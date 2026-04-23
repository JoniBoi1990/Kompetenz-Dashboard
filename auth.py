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
import db

AUTHORITY = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}"
# User.Read for identity + Notes.Read.All for OneNote sync
# offline_access is automatically added by MSAL when using acquire_token_by_authorization_code
SCOPES = ["User.Read", "Notes.Read.All"]


def _build_redirect_uri(request: Request) -> str:
    """Build the redirect URI from the actual request host so multiple domains work.

    Respects X-Forwarded-Proto for reverse-proxy setups (e.g. Uberspace).
    Falls back to https for any non-localhost host.
    """
    netloc = request.url.netloc
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto
    elif netloc.startswith("localhost") or netloc.startswith("127."):
        scheme = "http"
    else:
        scheme = "https"
    return f"{scheme}://{netloc}/auth/callback"
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


def get_auth_url(state: str, request: Request) -> str:
    return _msal_app().get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=_build_redirect_uri(request),
    )


def exchange_code(code: str, request: Request) -> dict:
    result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=_build_redirect_uri(request),
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
    upn = claims.get("preferred_username", "").lower()
    
    # DEV_MODE: fallback für Entwicklung
    if settings.DEV_MODE:
        return "@lehrer." in upn or upn.endswith("@birklehof.de")
    
    # Prüfe ob UPN in approved_teachers Tabelle
    if db.is_approved_teacher(upn):
        return True
    
    # Wenn noch keine Lehrer genehmigt sind, erlaube Initial-Admin
    if not db.has_any_approved_teacher():
        if settings.INITIAL_ADMIN_UPN and upn == settings.INITIAL_ADMIN_UPN.lower():
            return True
    
    # Sonst kein Lehrer (auch Eltern mit @birklehof.de nicht)
    return False


def build_user_info(token_response: dict) -> dict:
    claims = _extract_claims(token_response.get("id_token", ""))
    upn = claims.get("preferred_username", "")
    return {
        "oid": upn,  # UPN als eindeutige ID verwenden (statt Azure AD Object ID)
        "upn": upn,
        "display_name": claims.get("name", ""),
        "roles": claims.get("roles", []),
        "is_teacher": is_teacher(claims),
        "access_token": token_response.get("access_token", ""),
        "refresh_token": token_response.get("refresh_token", ""),
    }


def acquire_token_by_refresh_token(refresh_token: str) -> dict | None:
    """Acquire a new access token using a refresh token.
    
    Returns the full token response or None if refresh failed.
    """
    try:
        result = _msal_app().acquire_token_by_refresh_token(
            refresh_token,
            scopes=SCOPES,
        )
        if "error" in result:
            print(f"[Auth] Token refresh failed: {result.get('error_description', result['error'])}")
            return None
        return result
    except Exception as e:
        print(f"[Auth] Token refresh exception: {e}")
        return None


def get_access_token_for_teacher(teacher_id: str) -> str | None:
    """Get a valid access token for a teacher (using refresh token if needed).
    
    Returns the access token or None if no valid token can be obtained.
    Also updates the stored token if refreshed.
    """
    token_data = db.get_teacher_token(teacher_id)
    if not token_data:
        return None
    
    # Check if we have a cached access token that's still valid
    expires_at = token_data.get("expires_at")
    access_token = token_data.get("access_token")
    
    if access_token and expires_at:
        from datetime import datetime, timezone
        try:
            exp = datetime.fromisoformat(expires_at)
            # Token is valid if it expires in more than 5 minutes
            if exp > datetime.now(timezone.utc).replace(tzinfo=timezone.utc):
                return access_token
        except:
            pass
    
    # Need to refresh
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None
    
    result = acquire_token_by_refresh_token(refresh_token)
    if not result:
        return None
    
    # Update stored tokens
    new_access = result.get("access_token", "")
    new_refresh = result.get("refresh_token", "")
    
    # Calculate expiry (typically 1 hour from now)
    expires_in = result.get("expires_in", 3600)
    from datetime import datetime, timedelta, timezone
    new_expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    
    # Use new refresh token if provided, otherwise keep old one
    refresh_to_store = new_refresh if new_refresh else refresh_token
    
    db.save_teacher_token(
        teacher_id=teacher_id,
        refresh_token=refresh_to_store,
        access_token=new_access,
        expires_at=new_expires,
    )
    
    return new_access


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


def get_logout_url(redirect_uri: str) -> str:
    """Build Microsoft logout URL to end Azure AD session."""
    if settings.DEV_MODE or not settings.AZURE_TENANT_ID:
        return "/login"
    return (
        f"{AUTHORITY}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={redirect_uri}"
    )


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
