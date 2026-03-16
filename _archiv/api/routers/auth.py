import secrets
from datetime import datetime

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from auth.msal_client import get_auth_url, exchange_code
from auth.jwt_validator import validate_id_token, is_teacher_from_claims
from auth.dependencies import get_current_user
from db.session import get_db
from models.models import User
from schemas.schemas import UserOut
from config import settings

router = APIRouter()


@router.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(get_auth_url(state))


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    if state != request.session.pop("oauth_state", None):
        return Response("Invalid state", status_code=400)

    token_result = exchange_code(code)
    claims = await validate_id_token(token_result["id_token"])

    async for db in get_db():
        stmt = pg_insert(User).values(
            azure_oid=claims["oid"],
            upn=claims["upn"],
            display_name=claims["display_name"],
            is_teacher=is_teacher_from_claims(claims),
            last_login=datetime.utcnow(),
        ).on_conflict_do_update(
            index_elements=["azure_oid"],
            set_={
                "upn": claims["upn"],
                "display_name": claims["display_name"],
                "is_teacher": is_teacher_from_claims(claims),
                "last_login": datetime.utcnow(),
            },
        ).returning(User.id)
        result = await db.execute(stmt)
        user_id = result.scalar_one()
        await db.commit()

    request.session["user_id"] = str(user_id)
    return RedirectResponse(f"https://{settings.DOMAIN}/")


@router.get("/me", response_model=UserOut)
async def me(request: Request):
    async for db in get_db():
        user = await get_current_user(request, db)
        return UserOut.model_validate(user)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "logged out"}
