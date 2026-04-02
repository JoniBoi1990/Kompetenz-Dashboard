from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOMAIN: str = "localhost:8000"
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_TENANT_ID: str = ""
    SESSION_SECRET: str = "dev-secret-not-for-production"
    # DEV_MODE=true → Login-Button setzt sofort eine Fake-Session (kein Azure nötig)
    DEV_MODE: bool = False
    USE_BOOKINGS_API: bool = False
    BOOKINGS_BUSINESS_ID: str = ""
    BOOKINGS_PAGE_URL: str = ""
    # SharePoint site ID that holds the MS Lists for competency records
    SHAREPOINT_SITE_ID: str = ""
    # Initial admin UPN for first-time setup (can be removed after adding teachers)
    INITIAL_ADMIN_UPN: str = "jonas.haut@birklehof.de"

    class Config:
        env_file = ".env"


settings = Settings()
