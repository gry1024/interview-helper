"""Application configuration loaded exclusively from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_base_url: str = os.getenv("MINIMAX_BASE_URL", "")
    minimax_model: str = os.getenv("MINIMAX_MODEL", "")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _get_int("APP_PORT", 80)
    clone_timeout_sec: int = _get_int("CLONE_TIMEOUT_SEC", 60)
    clone_max_mb: int = _get_int("CLONE_MAX_MB", 80)


settings = Settings()
