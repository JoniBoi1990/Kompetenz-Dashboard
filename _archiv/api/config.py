from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOMAIN: str = "dashboard.schule.de"
    AZURE_CLIENT_ID: str
    AZURE_CLIENT_SECRET: str
    AZURE_TENANT_ID: str
    SESSION_SECRET: str
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    PDF_WORKER_URL: str = "http://pdf-worker:8001"
    PDF_STORAGE_PATH: str = "/pdfs"
    USE_BOOKINGS_API: bool = False
    BOOKINGS_BUSINESS_ID: str = ""
    BOOKINGS_PAGE_URL: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
