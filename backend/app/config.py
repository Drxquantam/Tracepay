"""App settings, read from environment variables (see docker-compose.yml).

Payment *rules* (turnaround times, compensation rates) will live in a separate rules file
added in Phase 3, so the regulation-modelled values sit in one place.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Defaults point at the Compose Postgres exposed on host port 5433,
    # so tests can also run from outside Docker.
    database_url: str = "postgresql+asyncpg://tracepay:tracepay@localhost:5433/tracepay"
    test_database_url: str = "postgresql+asyncpg://tracepay:tracepay@localhost:5433/tracepay_test"

    db_pool_size: int = 20
    db_max_overflow: int = 20

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # bcrypt cost factor (2^rounds iterations). 12 is a sensible production-style default;
    # the test suite sets 4 so its many logins don't take minutes.
    bcrypt_rounds: int = 12

    # The periodic deadline sweep. Tests turn it off and call the sweep directly.
    run_background_jobs: bool = True

    cors_origins: str = "http://localhost:5173"  # comma-separated


settings = Settings()
