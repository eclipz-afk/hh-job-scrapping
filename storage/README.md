# Storage Service

PostgreSQL initialization scripts live in `storage/init/`.

Currently included:

- `001_bootstrap.sql`: enables `pg_trgm` extension.

Core application tables are created by SQLAlchemy at backend startup.
