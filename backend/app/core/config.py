import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url


@dataclass(slots=True)
class Settings:
    database_url: str | None = field(repr=False)
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str = field(repr=False)
    flask_host: str
    flask_port: int
    api_prefix: str
    cors_origins: list[str]
    target_cleaned_rows: int
    max_source_pages: int
    request_timeout_seconds: int
    etl_api_token: str = field(default="", repr=False)

    @property
    def sqlalchemy_database_uri(self) -> URL:
        if self.database_url:
            url = make_url(self.database_url)
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            if url.drivername != "postgresql+psycopg":
                raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
            return url
        if not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD must be configured")
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def load_settings() -> Settings:
    load_dotenv()
    cors_value = os.getenv("CORS_ORIGINS", "http://localhost:8080")
    cors_origins = []
    for origin in cors_value.split(","):
        origin = origin.strip()
        if origin:
            cors_origins.append(origin)

    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=_get_int("POSTGRES_PORT", 5432),
        postgres_db=os.getenv("POSTGRES_DB", "jobsdb"),
        postgres_user=os.getenv("POSTGRES_USER", "jobs"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
        flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
        flask_port=_get_int("FLASK_PORT", 5000),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        cors_origins=cors_origins,
        target_cleaned_rows=_get_int("TARGET_CLEANED_ROWS", 5000),
        max_source_pages=_get_int("MAX_SOURCE_PAGES", 120),
        request_timeout_seconds=_get_int("REQUEST_TIMEOUT_SECONDS", 20),
        etl_api_token=os.getenv("ETL_API_TOKEN", ""),
    )
