import httpx
from config import settings


async def request_pdf(payload: dict) -> bytes:
    """Call the internal pdf-worker and return PDF bytes."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{settings.PDF_WORKER_URL}/generate", json=payload)
        resp.raise_for_status()
        return resp.content
