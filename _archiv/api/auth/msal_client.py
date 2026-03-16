import msal
from config import settings

AUTHORITY = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}"
SCOPES = ["openid", "profile", "email", "User.Read"]
BOOKINGS_SCOPES = ["BookingsAppointment.ReadWrite.All"]
REDIRECT_URI = f"https://{settings.DOMAIN}/auth/callback"


def get_msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=settings.AZURE_CLIENT_ID,
        client_credential=settings.AZURE_CLIENT_SECRET,
        authority=AUTHORITY,
    )


def get_auth_url(state: str) -> str:
    app = get_msal_app()
    return app.get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )


def exchange_code(code: str) -> dict:
    app = get_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    if "error" in result:
        raise ValueError(f"Token exchange failed: {result.get('error_description', result['error'])}")
    return result
