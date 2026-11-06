# Security

## Local access and secrets

- Local Docker ports bind to `127.0.0.1`; pgAdmin uses `127.0.0.1:5433`.
- `.env` is ignored by Git and excluded from Docker build contexts.
- PostgreSQL requires an explicitly configured password. Use a unique password.
- `ETL_API_TOKEN` protects ingestion; an empty value disables HTTP ingestion.
  Generate it with `py scripts/init_etl_token.py`. Its value is never printed.
- The dashboard asks for the token in a password field and uses it only for that
  request. No token is embedded in static JavaScript, URLs, or browser storage.
- Prefer a database role scoped to this application's database. The application
  currently creates tables at startup, so it needs schema creation privileges.
- A password previously included in chat or terminal transcripts must be rotated
  even if it was never committed. Changing `.env` alone does not change an existing
  PostgreSQL role's password. Rotate the role password and configuration together;
  do not delete the data volume as a way to change credentials.

## Application controls

- Scraped data is rendered with text nodes; links accept only HTTP/HTTPS without
  embedded credentials and suppress referrer/opener access.
- Third-party JavaScript uses exact versions and SHA-384 integrity checks.
- CSP, frame restrictions, MIME sniffing prevention and referrer restrictions are
  configured on the frontend/API. If deployment domains change, update the CSP
  `connect-src` and `CORS_ORIGINS` together.
- ETL uses constant-time bearer-token checks, a 16 KiB body limit, a 10000-row
  request limit and a PostgreSQL advisory transaction lock across workers.
- Request parameters are bounded. Database queries use SQLAlchemy parameters.
  Database statements time out after 30 seconds; external requests have timeouts.
- HTTP errors and unexpected failures return generic JSON without credentials,
  SQL parameters or stack traces. Settings representations hide secrets.
- The direct Python entry point disables the Werkzeug debugger. Use Gunicorn in
  deployment. The backend container runs as a non-root user.
- Fetch URLs use fixed provider hosts; HH detail IDs must be numeric and provider
  requests do not follow redirects to arbitrary hosts.

## Audit (2026-11-06)

The source review identified stored XSS, unprotected ingestion, unrestricted local
port publishing, development debugger exposure and weak credential defaults.
These were addressed in code/configuration with regression coverage.

The initial dependency scan identified three distinct known advisories affecting
`python-dotenv` 1.1.1, `requests` 2.32.5 and `pytest` 8.4.2. The requirement pins
were updated to 1.2.2, 2.34.2 and 9.0.3 respectively. A repeat `pip-audit` scan
reported no known vulnerabilities in the resolved Python dependencies.

`scripts/check_secrets.py` scans working files, staged versions, Git configuration
and blob objects in history reachable from all local refs. It checks common token
formats and compares content against secrets in the local `.env`, without printing
secret values. No matching secrets were found. This is a heuristic scan: it does
not cover deleted remote branches, GitHub caches, other repositories or chat logs.

Bandit reported no issues in the application Python source at the time of review.
Docker Scout was available but required Docker Hub authentication, so the
container OS/package CVE scan could not run. No Docker account was connected.
These checks do not prove the absence of every vulnerability. OS/container packages,
hosting configuration and future dependency advisories require ongoing review.

## Verification

```powershell
py -m pytest backend/tests -q
node --test frontend/tests/security.test.cjs
py scripts/check_secrets.py
py scripts/verify_security.py
```

For a fresh dependency check, install `pip-audit` in a separate audit environment
and run `pip-audit -r backend/requirements.txt`. Audit tools and raw reports are
ignored by Git. Keep report output private if it contains deployment metadata.

Rebuild/recreate services after changing code or bindings:

```powershell
docker compose up -d --build
```

Do not use `docker compose down -v`; it deletes the persistent database volume.
