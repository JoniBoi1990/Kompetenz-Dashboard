import httpx
from jose import jwt, JWTError
from config import settings

JWKS_URI = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/v2.0"

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JWKS_URI)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def validate_id_token(id_token: str) -> dict:
    jwks = await _get_jwks()
    try:
        claims = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=settings.AZURE_CLIENT_ID,
            issuer=ISSUER,
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise ValueError(f"JWT validation failed: {e}")

    return {
        "oid": claims["oid"],
        "upn": claims.get("preferred_username") or claims.get("upn", ""),
        "display_name": claims.get("name", ""),
        "roles": claims.get("roles", []),
    }


def is_teacher_from_claims(claims: dict) -> bool:
    if "Lehrer" in claims.get("roles", []):
        return True
    upn = claims.get("upn", "")
    return "@lehrer." in upn
