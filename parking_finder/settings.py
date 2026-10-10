"""Environment configuration. No secrets are required."""

import os
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://verkehr.autobahn.de/o/autobahn"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """Load a local .env file without overriding variables already set."""
    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_trust_store() -> None:
    """Use the operating-system certificate store when it is available.

    Python's default CA bundle misses root certificates that Windows already
    trusts (common on company laptops). ``truststore`` fixes that without
    turning verification off.
    """
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    open_browser: bool
    timeout: float
    ssl_verify: bool
    base_url: str
    on_air: bool


def load_settings() -> Settings:
    load_dotenv()
    try:
        port = int(os.environ.get("PORT", "8080"))
    except ValueError as exc:
        raise SystemExit("PORT must be a whole number, for example 8080.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535.")
    try:
        timeout = float(os.environ.get("AUTOBAHN_TIMEOUT", "20"))
    except ValueError as exc:
        raise SystemExit("AUTOBAHN_TIMEOUT must be a number of seconds.") from exc
    if timeout <= 0:
        raise SystemExit("AUTOBAHN_TIMEOUT must be greater than 0.")
    ssl_verify = _flag("AUTOBAHN_SSL_VERIFY", True)
    if ssl_verify:
        configure_trust_store()
    return Settings(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=port,
        open_browser=_flag("OPEN_BROWSER", True),
        timeout=timeout,
        ssl_verify=ssl_verify,
        base_url=os.environ.get("AUTOBAHN_BASE_URL", BASE_URL).rstrip("/"),
        on_air=_flag("ON_AIR", False),
    )
