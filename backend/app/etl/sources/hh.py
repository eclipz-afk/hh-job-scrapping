from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.etl.sources.base import parse_datetime
from app.etl.types import RawJob


class HHSource:
    name = "hh"
    base_url = "https://api.hh.ru/vacancies"
    search_url = "https://hh.ru/search/vacancy"

    _VACANCY_ID_RE = re.compile(r"/vacancy/(?P<id>\d+)")
    _SALARY_NUMBER_RE = re.compile(r"\d[\d\s]*")
    _META_DESCRIPTION_RE = re.compile(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        flags=re.IGNORECASE,
    )
    _JSON_LD_RE = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        flags=re.DOTALL | re.IGNORECASE,
    )

    _COUNTRY_CODE_MAP: dict[str, str] = {
        "RU": "Russia",
        "BY": "Belarus",
        "KZ": "Kazakhstan",
        "UA": "Ukraine",
        "AM": "Armenia",
        "GE": "Georgia",
        "KG": "Kyrgyzstan",
        "UZ": "Uzbekistan",
        "AZ": "Azerbaijan",
        "MD": "Moldova",
    }

    _COUNTRY_HINTS: dict[str, tuple[str, ...]] = {
        "Belarus": ("минск", "брест", "гродно", "гомель", "витебск", "могилев", "belarus"),
        "Kazakhstan": ("алматы", "астана", "шымкент", "караганда", "актау", "атырау", "kazakhstan"),
        "Armenia": ("ереван", "armenia"),
        "Georgia": ("тбилиси", "батуми", "georgia"),
        "Kyrgyzstan": ("бишкек", "kyrgyzstan"),
        "Uzbekistan": ("ташкент", "узбекистан", "uzbekistan"),
        "Azerbaijan": ("баку", "azerbaijan"),
    }

    _QUERIES = (
        "data scientist",
        "machine learning engineer",
        "computer vision engineer",
        "nlp engineer",
        "mlops engineer",
        "data analyst",
        "data engineer",
        "bi analyst",
        "etl developer",
        "sql developer",
        "ml engineer",
        "аналитик данных",
        "инженер данных",
        "ml инженер",
        "дата сайентист",
        "python developer",
        "backend developer",
        "frontend developer",
        "fullstack developer",
        "java developer",
        "golang developer",
        "c++ developer",
        "php developer",
        "node.js developer",
        "react developer",
        "android developer",
        "ios developer",
        "devops engineer",
        "site reliability engineer",
        "cloud engineer",
        "security engineer",
        "network engineer",
        "qa engineer",
        "software engineer",
        "business analyst",
        "system analyst",
        "postgresql dba",
        "hadoop engineer",
        "spark engineer",
        "системный аналитик",
        "бизнес аналитик",
        "разработчик java",
        "разработчик golang",
        "разработчик c++",
        "разработчик 1с",
        "devops инженер",
        "инженер по тестированию",
        "python разработчик",
        "backend разработчик",
        "тестировщик",
    )

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.detail_enrich_budget = 500
        self.salary_enrich_target = 90

    def fetch_jobs(self, target_rows: int, max_pages: int) -> list[RawJob]:
        seen_ids: set[str] = set()
        results: list[RawJob] = []

        api_rows = self._fetch_via_api(
            target_rows=target_rows,
            max_pages=max_pages,
            seen_ids=seen_ids,
        )
        results.extend(api_rows)

        if len(results) < target_rows:
            html_rows = self._fetch_via_html(
                target_rows=target_rows - len(results),
                max_pages=max_pages,
                seen_ids=seen_ids,
            )
            results.extend(html_rows)

        return results[:target_rows]

    def _fetch_via_api(self, target_rows: int, max_pages: int, seen_ids: set[str]) -> list[RawJob]:
        headers = {"User-Agent": "job-analytics-dashboard/1.0"}
        max_pages_per_query = max(1, max_pages // max(len(self._QUERIES), 1))
        results: list[RawJob] = []

        with requests.Session() as client:
            client.headers.update(headers)
            client.trust_env = False
            for query in self._QUERIES:
                for page in range(max_pages_per_query):
                    if len(results) >= target_rows:
                        return results

                    params = {
                        "text": query,
                        "page": page,
                        "per_page": 100,
                        "order_by": "publication_time",
                        "only_with_salary": "false",
                    }
                    try:
                        response = client.get(self.base_url, params=params, timeout=self.timeout_seconds, allow_redirects=False)
                    except requests.RequestException:
                        break

                    if response.status_code in {400, 401, 403}:
                        break

                    try:
                        response.raise_for_status()
                        payload = response.json()
                    except (requests.RequestException, ValueError):
                        break

                    items = payload.get("items") or []
                    if not items:
                        break

                    for item in items:
                        parsed = self._parse_api_item(item)
                        if parsed is None or parsed.external_id in seen_ids:
                            continue
                        seen_ids.add(parsed.external_id)
                        results.append(parsed)

        return results

    def _fetch_via_html(self, target_rows: int, max_pages: int, seen_ids: set[str]) -> list[RawJob]:
        headers = {"User-Agent": "Mozilla/5.0"}
        page_budget = max(30, max_pages * 5)
        page_per_query: dict[str, int] = {query: 0 for query in self._QUERIES}
        exhausted_queries: set[str] = set()
        results: list[RawJob] = []
        pages_used = 0
        detail_requests = 0
        salary_enriched = 0

        with requests.Session() as client:
            client.headers.update(headers)
            client.trust_env = False

            while (
                len(results) < target_rows
                and len(exhausted_queries) < len(self._QUERIES)
                and pages_used < page_budget
            ):
                for query in self._QUERIES:
                    if query in exhausted_queries or pages_used >= page_budget or len(results) >= target_rows:
                        continue

                    page = page_per_query[query]
                    page_per_query[query] += 1
                    pages_used += 1

                    params = {
                        "text": query,
                        "page": page,
                        "search_field": "name",
                    }
                    try:
                        response = client.get(self.search_url, params=params, timeout=self.timeout_seconds, allow_redirects=False)
                        response.raise_for_status()
                    except requests.RequestException:
                        exhausted_queries.add(query)
                        continue

                    rows = self._parse_html_cards(response.text)
                    if not rows:
                        exhausted_queries.add(query)
                        continue

                    for row in rows:
                        if row.external_id in seen_ids:
                            continue
                        seen_ids.add(row.external_id)

                        if detail_requests < self.detail_enrich_budget and salary_enriched < self.salary_enrich_target and (
                            row.salary_from is None or row.salary_to is None
                        ):
                            detail_requests += 1
                            enriched = self._enrich_from_vacancy_page(client, row)
                            if enriched is not None:
                                row = enriched
                                if row.salary_from is not None or row.salary_to is not None:
                                    salary_enriched += 1

                        results.append(row)
                        if len(results) >= target_rows:
                            break

                    time.sleep(0.08)

        return results

    def _parse_api_item(self, item: dict[str, Any]) -> RawJob | None:
        external_id = item.get("id")
        title = item.get("name")
        employer = (item.get("employer") or {}).get("name")
        area = item.get("area") or {}
        location = area.get("name") or "unknown"

        if not external_id or not title or not employer:
            return None

        salary = item.get("salary") or {}
        salary_from = self._to_float(salary.get("from"))
        salary_to = self._to_float(salary.get("to"))
        salary_currency = salary.get("currency")

        address = item.get("address") or {}
        city = address.get("city")

        snippet = item.get("snippet") or {}
        description = " ".join(
            part for part in [snippet.get("requirement"), snippet.get("responsibility")] if part
        ).strip() or None

        return RawJob(
            source=self.name,
            external_id=str(external_id),
            title=str(title),
            company=str(employer),
            location=str(location),
            country=self._infer_country(str(location)),
            city=city or self._guess_city(str(location)),
            employment_type=(item.get("employment") or {}).get("name"),
            remote_type=(item.get("schedule") or {}).get("name"),
            salary_from=salary_from,
            salary_to=salary_to,
            salary_currency=salary_currency,
            published_at=parse_datetime(item.get("published_at")),
            url=item.get("alternate_url") or "https://hh.ru/",
            description=description,
        )

    @staticmethod
    def _parse_html_cards(html: str) -> list[RawJob]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('[data-qa="vacancy-serp__vacancy"]')
        jobs: list[RawJob] = []

        for card in cards:
            title_node = card.select_one('[data-qa="serp-item__title"]')
            if title_node is None:
                continue

            href = (title_node.get("href") or "").strip()
            match = HHSource._VACANCY_ID_RE.search(href)
            if not match:
                continue

            external_id = match.group("id")
            title = title_node.get_text(" ", strip=True)
            if not title:
                continue

            company_node = (
                card.select_one('[data-qa="vacancy-serp__vacancy-employer-text"]')
                or card.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
            )
            company = company_node.get_text(" ", strip=True) if company_node else "unknown"

            location_node = card.select_one('[data-qa="vacancy-serp__vacancy-address"]')
            location = location_node.get_text(" ", strip=True) if location_node else "unknown"

            salary_node = card.select_one('[data-qa^="vacancy-serp__vacancy-compensation"]')
            salary_text = salary_node.get_text(" ", strip=True) if salary_node else ""
            salary_from, salary_to, salary_currency = HHSource._parse_salary_text(salary_text)

            remote_type = "Remote" if "удален" in card.get_text(" ", strip=True).lower() else None

            jobs.append(
                RawJob(
                    source=HHSource.name,
                    external_id=external_id,
                    title=title,
                    company=company or "unknown",
                    location=location or "unknown",
                    country=HHSource._infer_country(location),
                    city=HHSource._guess_city(location),
                    employment_type=None,
                    remote_type=remote_type,
                    salary_from=salary_from,
                    salary_to=salary_to,
                    salary_currency=salary_currency,
                    published_at=None,
                    url=f"https://hh.ru/vacancy/{external_id}",
                    description=None,
                )
            )

        return jobs

    def _enrich_from_vacancy_page(self, client: requests.Session, row: RawJob) -> RawJob | None:
        if not re.fullmatch(r"[0-9]{1,20}", row.external_id):
            return None
        url = f"https://hh.ru/vacancy/{row.external_id}"
        try:
            response = client.get(url, timeout=self.timeout_seconds, allow_redirects=False)
            response.raise_for_status()
        except requests.RequestException:
            return None

        html = response.text
        salary_from = row.salary_from
        salary_to = row.salary_to
        salary_currency = row.salary_currency
        country = row.country
        city = row.city

        meta_match = self._META_DESCRIPTION_RE.search(html)
        if meta_match:
            description_meta = meta_match.group(1)
            meta_salary = self._salary_from_meta_description(description_meta)
            if meta_salary is not None:
                salary_from = meta_salary[0] if meta_salary[0] is not None else salary_from
                salary_to = meta_salary[1] if meta_salary[1] is not None else salary_to
                salary_currency = meta_salary[2] or salary_currency

        json_ld_match = self._JSON_LD_RE.search(html)
        if json_ld_match:
            try:
                payload = json.loads(json_ld_match.group(1))
            except (json.JSONDecodeError, TypeError):
                payload = None

            if isinstance(payload, dict):
                location_payload = payload.get("jobLocation")
                address = location_payload.get("address") if isinstance(location_payload, dict) else None
                if isinstance(address, dict):
                    country_code = address.get("addressCountry")
                    country = self._country_from_code(country_code) or country
                    city = address.get("addressLocality") or city

        return RawJob(
            source=row.source,
            external_id=row.external_id,
            title=row.title,
            company=row.company,
            location=row.location,
            country=country,
            city=city,
            employment_type=row.employment_type,
            remote_type=row.remote_type,
            salary_from=salary_from,
            salary_to=salary_to,
            salary_currency=salary_currency,
            published_at=row.published_at,
            url=row.url,
            description=row.description,
        )

    @staticmethod
    def _salary_from_meta_description(description_meta: str) -> tuple[float | None, float | None, str | None] | None:
        marker = "Зарплата:"
        idx = description_meta.find(marker)
        if idx == -1:
            return None

        fragment = description_meta[idx + len(marker) :].strip()
        segment = fragment.split(".", maxsplit=1)[0].strip()
        if not segment:
            return None

        return HHSource._parse_salary_text(segment)

    @staticmethod
    def _country_from_code(code: str | None) -> str | None:
        if not code:
            return None
        return HHSource._COUNTRY_CODE_MAP.get(code.upper())

    @staticmethod
    def _infer_country(location: str) -> str:
        normalized = (location or "").lower().replace("\xa0", " ").strip()
        if not normalized:
            return "Russia"

        if "беларус" in normalized or "belarus" in normalized:
            return "Belarus"
        if "казахстан" in normalized or "kazakhstan" in normalized:
            return "Kazakhstan"
        if "армени" in normalized or "armenia" in normalized:
            return "Armenia"
        if "грузи" in normalized or "georgia" in normalized:
            return "Georgia"
        if "узбекистан" in normalized or "uzbekistan" in normalized:
            return "Uzbekistan"
        if "кыргыз" in normalized or "kyrgyzstan" in normalized:
            return "Kyrgyzstan"
        if "азербайдж" in normalized or "azerbaijan" in normalized:
            return "Azerbaijan"

        for country, hints in HHSource._COUNTRY_HINTS.items():
            for hint in hints:
                if normalized.startswith(hint) or f", {hint}" in normalized:
                    return country

        return "Russia"

    @staticmethod
    def _parse_salary_text(text: str) -> tuple[float | None, float | None, str | None]:
        normalized = (text or "").replace("\xa0", " ").strip().lower()
        if not normalized:
            return None, None, None

        raw_numbers = HHSource._SALARY_NUMBER_RE.findall(normalized)
        numbers = [float(value.replace(" ", "")) for value in raw_numbers if value.strip()]
        if not numbers:
            return None, None, None

        currency = None
        if "руб" in normalized or "rur" in normalized or "rub" in normalized or "₽" in normalized:
            currency = "RUR"
        elif "$" in normalized or "usd" in normalized:
            currency = "USD"
        elif "eur" in normalized or "€" in normalized:
            currency = "EUR"
        elif "kzt" in normalized or "₸" in normalized:
            currency = "KZT"
        elif "byn" in normalized:
            currency = "BYN"

        if "от" in normalized and numbers:
            return numbers[0], None, currency
        if "до" in normalized and numbers:
            return None, numbers[0], currency
        if len(numbers) >= 2:
            return numbers[0], numbers[1], currency

        return numbers[0], None, currency

    @staticmethod
    def _guess_city(location: str) -> str | None:
        cleaned = (location or "").replace("\xa0", " ").strip()
        if not cleaned or cleaned.lower() == "unknown":
            return None
        city = cleaned.split(",", maxsplit=1)[0].strip()
        return city or None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
