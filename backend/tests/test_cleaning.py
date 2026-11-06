from app.etl.cleaning import clean_raw_job
from app.etl.types import RawJob


def test_clean_raw_job_returns_expected_structure() -> None:
    raw = RawJob(
        source="hh",
        external_id="123",
        title="Data Scientist",
        company="Acme",
        location="Moscow",
        country="Russia",
        city="Moscow",
        employment_type="Full-time",
        remote_type="Remote",
        salary_from=200000,
        salary_to=300000,
        salary_currency="RUR",
        published_at=None,
        url="https://example.com/job/123",
        description="Python, SQL, and machine learning experience required",
    )

    cleaned = clean_raw_job(raw)

    assert cleaned is not None
    assert cleaned.role_family == "data_science"
    assert "python" in cleaned.skills
    assert cleaned.salary_usd_from is not None


def test_clean_raw_job_drops_invalid_rows() -> None:
    raw = RawJob(
        source="hh",
        external_id="124",
        title="",
        company="Acme",
        location="Moscow",
        country="Russia",
        city="Moscow",
        employment_type=None,
        remote_type=None,
        salary_from=None,
        salary_to=None,
        salary_currency=None,
        published_at=None,
        url="https://example.com/job/124",
        description=None,
    )

    assert clean_raw_job(raw) is None
