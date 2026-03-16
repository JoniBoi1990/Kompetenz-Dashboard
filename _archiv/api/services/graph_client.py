import httpx
import msal
from config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTHORITY = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}"


async def get_app_token(scopes: list[str]) -> str:
    """Acquire a client-credentials token for Graph API calls."""
    app = msal.ConfidentialClientApplication(
        client_id=settings.AZURE_CLIENT_ID,
        client_credential=settings.AZURE_CLIENT_SECRET,
        authority=AUTHORITY,
    )
    result = app.acquire_token_for_client(scopes=scopes)
    if "access_token" not in result:
        raise RuntimeError(f"Graph token error: {result.get('error_description', result)}")
    return result["access_token"]


async def graph_get(path: str, scopes: list[str]) -> dict:
    token = await get_app_token(scopes)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def graph_post(path: str, body: dict, scopes: list[str]) -> dict:
    token = await get_app_token(scopes)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}{path}",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def graph_delete(path: str, scopes: list[str]) -> None:
    token = await get_app_token(scopes)
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
