import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Simple environment-driven settings. No secrets are ever logged."""

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://localhost/approval_service"
    )
    ENV: str = os.getenv("ENV", "development")


settings = Settings()