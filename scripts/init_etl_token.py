"""Create an ETL token in the ignored local .env without printing it."""

from pathlib import Path
import re
import secrets


def main() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        raise SystemExit("Create .env from .env.example first.")
    content = env_file.read_text(encoding="utf-8-sig")
    pattern = re.compile(r"^ETL_API_TOKEN\s*=.*$", re.MULTILINE)
    match = pattern.search(content)
    if match and match.group().split("=", 1)[1].strip().strip("\"'"):
        print("ETL_API_TOKEN is already configured; unchanged.")
        return
    setting = "ETL_API_TOKEN=" + secrets.token_urlsafe(48)
    content = pattern.sub(setting, content) if match else content.rstrip() + "\n\n" + setting + "\n"
    env_file.write_text(content, encoding="utf-8")
    print("ETL_API_TOKEN configured in .env; value not printed.")


if __name__ == "__main__":
    main()
