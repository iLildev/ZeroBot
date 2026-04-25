from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/zerobot"

    # Crystals
    INITIAL_CRYSTALS: int = 10

    # Ports
    PORT_RANGE_START: int = 30000
    PORT_RANGE_END: int = 30100

    # Admin Console
    ADMIN_TOKEN: str = ""           # required to use any /admin/* endpoint
    ADMIN_USER_ID: str = ""         # the developer's user id (owner of official bots)

    class Config:
        env_file = ".env"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_async_url(cls, v: str) -> str:
        """Force asyncpg driver and drop unsupported query params (e.g. sslmode)."""
        parsed = urlparse(v)
        scheme = parsed.scheme
        if scheme == "postgres" or scheme == "postgresql":
            scheme = "postgresql+asyncpg"
        query = dict(parse_qsl(parsed.query))
        query.pop("sslmode", None)
        return urlunparse(parsed._replace(scheme=scheme, query=urlencode(query)))


settings = Settings()
