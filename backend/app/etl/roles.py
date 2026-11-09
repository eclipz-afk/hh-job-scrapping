"""Role labels for charts, not vacancy availability checks or exclusion rules."""

import re


def _compile_pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.IGNORECASE)


DATA_ROLE = _compile_pattern(
    r"\bdata[\s-]+(?:scientist|science|engineer|analyst|analytics|architect|platform|warehouse)\b|"
    r"\b(?:machine|deep)[\s-]+learning\b|\b(?:ml|ai|llm|nlp|mlops|llmops|dwh|etl)\b|"
    r"\bcomputer[\s-]+vision\b|\b(?:bi|business intelligence)[\s-]*(?:analyst|developer|engineer)\b|"
    r"аналитик\w*\s+данных|инженер\w*\s+данных|машинн[а-я]*\s+(?:обучен|зрени)|"
    r"(?:bi|би)[\s-]*аналитик|дата[\s-]*(?:саентист|инженер|аналитик)|"
    r"компьютерн[а-я]*\s+зрени|искусственн[а-я]*\s+интеллект"
)


def classify_role(title: str) -> str:
    title = (title or "").replace("\u2011", "-").replace("\u2013", "-")
    return "data_science" if DATA_ROLE.search(title) else "it"


def role_category(title: str, role_family: str) -> str:
    if role_family == "data_science":
        if _compile_pattern(
            r"data[\s-]+engineer|инженер\w*\s+данных|\b(?:etl|dwh|data platform)\b"
        ).search(title):
            return "Data engineering"
        if _compile_pattern(r"analyst|аналитик|\bbi\b|analytics").search(title):
            return "Data analysis & BI"
        return "Data science & ML"
    for label, regex in (
        ("DevOps & reliability", r"devops|devsecops|sre|reliability|девопс"),
        ("Quality assurance", r"\bqa\b|test|тестиров|тестирован"),
        ("Cybersecurity", r"security|безопасност|pentest"),
        ("IT & systems analysis", r"analyst|аналитик"),
        (
            "Infrastructure & support",
            r"network|cloud|infrastructure|системн|сетев|администр|поддержк|\bdba\b",
        ),
    ):
        if _compile_pattern(regex).search(title):
            return label
    return "Software development"
