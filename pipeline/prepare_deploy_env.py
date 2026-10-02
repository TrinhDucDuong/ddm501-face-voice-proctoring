"""Prepare a runner's deployment environment without logging secret values."""
import os
import re
from pathlib import Path


def prepare(directory: Path) -> None:
    values = {name: os.environ.get("DEPLOY_" + name, "")
              for name in ("POSTGRES_PASSWORD", "API_KEY")}
    for name, value in values.items():
        # Compose embeds the DB password in connection URLs and a shell command.
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", value):
            raise ValueError(f"{name} must contain at least 16 URL-safe letters, digits, '_' or '-'")
    destination = directory / ".env"
    source = destination if destination.exists() else directory / ".env.example"
    content = source.read_text(encoding="utf-8")
    existing = dict(line.split("=", 1) for line in content.splitlines()
                    if "=" in line and not line.startswith("#"))
    if destination.exists() and existing.get("POSTGRES_PASSWORD") != values["POSTGRES_PASSWORD"]:
        raise ValueError("POSTGRES_PASSWORD differs from existing deployment; migrate DB credentials before deploying")
    old_password = existing.get("POSTGRES_PASSWORD", "biometric_dev_only")
    content = content.replace(old_password, values["POSTGRES_PASSWORD"])
    for name, value in values.items():
        if re.search(rf"^{name}=", content, flags=re.MULTILINE):
            content = re.sub(rf"^{name}=.*$", f"{name}={value}", content, flags=re.MULTILINE)
        else:
            content += f"\n{name}={value}\n"
    destination.write_text(content, encoding="utf-8")
    destination.chmod(0o600)


if __name__ == "__main__":
    prepare(Path.cwd())
