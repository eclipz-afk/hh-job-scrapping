"""Check worktree, Git index and reachable history; never print secret values."""

import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "openai_token": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "database_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:([^@\s]+)@"),
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def local_secrets() -> list[str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return []
    values = []
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if not separator or key.lstrip().startswith("#"):
            continue
        value = value.strip().strip("\"'")
        if any(word in key.upper() for word in ("PASSWORD", "TOKEN", "SECRET", "API_KEY")) and len(value) >= 8:
            values.append(value)
        if key.strip() == "DATABASE_URL":
            password = urlsplit(value).password
            if password and len(password) >= 8:
                values.append(unquote(password))
    return values


def main() -> None:
    secrets = local_secrets()
    findings = []
    scanned = 0

    def scan(label: str, data: bytes) -> None:
        nonlocal scanned
        if b"\0" in data:
            return
        scanned += 1
        content = data.decode("utf-8", errors="replace")
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                # Ignore documented example URLs, never ignore actual local secrets.
                if kind == "database_password" and match.group(1) in {"jobs", "password", "PASSWORD"}:
                    continue
                findings.append({"location": label, "line": content.count("\n", 0, match.start()) + 1, "kind": kind})
        for secret in secrets:
            if secret in content:
                findings.append({"location": label, "kind": "local_env_secret"})

    tracked = git("ls-files", "-z").decode().split("\0")
    for name in filter(None, tracked):
        path = ROOT / name
        if path.is_file():
            scan("worktree:" + name, path.read_bytes())
        scan("index:" + name, git("show", ":" + name))
        if Path(name).name == ".env":
            findings.append({"location": name, "kind": "tracked_env_file"})
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    for name in filter(None, untracked):
        path = ROOT / name
        if path.is_file():
            scan("untracked:" + name, path.read_bytes())
    config_file = ROOT / ".git" / "config"
    if config_file.is_file():
        scan("git-config", config_file.read_bytes())
    history = git("rev-list", "--objects", "--all").decode().splitlines()
    for entry in history:
        object_id, _, name = entry.partition(" ")
        if name and git("cat-file", "-t", object_id).strip() == b"blob":
            scan("history:" + object_id[:12] + ":" + name, git("cat-file", "blob", object_id))
    print(json.dumps({"scanned_text_versions": scanned, "findings": findings}, indent=2))
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()
