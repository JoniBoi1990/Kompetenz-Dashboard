"""
MSAL auth + session handling.

Session is stored in a signed cookie via itsdangerous.
Cookie payload: { oid, upn, display_name, roles, access_token, id_token }
"""
import secrets
import httpx
import msal
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, status

from config import settings

AUTHORITY = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}"
REDIRECT_URI = (
    f"http://{settings.DOMAIN}/auth/callback"
    if settings.DOMAIN.startswith("localhost")
    else f"https://{settings.DOMAIN}/auth/callback"
)
# Scopes needed for Graph API calls (Groups/Members, Sites, Lists)
SCOPES = [
    "User.Read",
    "GroupMember.Read.All",
    "Sites.ReadWrite.All",
]

JWKS_URI = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/v2.0"

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)
_COOKIE_NAME = "session"
_COOKIE_MAX_AGE = 8 * 3600  # 8 hours


# ---------------------------------------------------------------------------
# MSAL helpers
# ---------------------------------------------------------------------------

def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=settings.AZURE_CLIENT_ID,
        client_credential=settings.AZURE_CLIENT_SECRET,
        authority=AUTHORITY,
    )


def get_auth_url(state: str) -> str:
    return _msal_app().get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )


def exchange_code(code: str) -> dict:
    result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    if "error" in result:
        raise ValueError(
            f"Token exchange failed: {result.get('error_description', result['error'])}"
        )
    return result


# ---------------------------------------------------------------------------
# JWT claims extraction (no full signature validation — MSAL already validated)
# ---------------------------------------------------------------------------

def _extract_claims(id_token: str) -> dict:
    """Decode (without verification) to read claims — MSAL already verified the token."""
    import base64, json
    parts = id_token.split(".")
    if len(parts) < 2:
        return {}
    # Add padding
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def is_teacher(claims: dict) -> bool:
    if "Lehrer" in claims.get("roles", []):
        return True
    return "@lehrer." in claims.get("preferred_username", "")


def build_user_info(token_response: dict) -> dict:
    claims = _extract_claims(token_response.get("id_token", ""))
    return {
        "oid": claims.get("oid", ""),
        "upn": claims.get("preferred_username", ""),
        "display_name": claims.get("name", ""),
        "roles": claims.get("roles", []),
        "is_teacher": is_teacher(claims),
        "access_token": token_response.get("access_token", ""),
    }


# ---------------------------------------------------------------------------
# Session cookie
# ---------------------------------------------------------------------------

def set_session(response, user_info: dict) -> None:
    cookie_value = _serializer.dumps(user_info)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=cookie_value,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.DOMAIN.startswith("localhost"),
    )


def clear_session(response) -> None:
    response.delete_cookie(_COOKIE_NAME)


def get_session(request: Request) -> dict | None:
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        return None
    try:
        return _serializer.loads(cookie, max_age=_COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def require_user(request: Request) -> dict:
    user = get_session(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})
    return user


def require_teacher_user(request: Request) -> dict:
    user = require_user(request)
    if not user.get("is_teacher"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Lehrkräfte")
    return user
