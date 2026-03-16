from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.dependencies import require_teacher, get_current_user
from db.session import get_db
from models.models import Competency, Question, User
from schemas.schemas import CompetencyOut, CompetencyPatch, QuestionOut, QuestionCreate

router = APIRouter()


@router.get("", response_model=list[CompetencyOut])
async def list_competencies(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Competency).where(Competency.is_active == True).order_by(Competency.display_order)
    )
    return [CompetencyOut.model_validate(c) for c in result.scalars().all()]


@router.patch("/{competency_id}", response_model=CompetencyOut)
async def patch_competency(
    competency_id: str,
    body: CompetencyPatch,
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Competency).where(Competency.id == competency_id))
    comp = result.scalar_one()
    if body.is_active is not None:
        comp.is_active = body.is_active
    if body.display_order is not None:
        comp.display_order = body.display_order
    return CompetencyOut.model_validate(comp)


@router.get("/{competency_id}/questions", response_model=list[QuestionOut])
async def get_questions(
    competency_id: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Question).where(
            Question.competency_id == competency_id,
            Question.is_active == True,
        )
    )
    return [QuestionOut.model_validate(q) for q in result.scalars().all()]


@router.post("/{competency_id}/questions", response_model=QuestionOut)
async def add_question(
    competency_id: str,
    body: QuestionCreate,
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    q = Question(competency_id=competency_id, text=body.text)
    db.add(q)
    await db.flush()
    return QuestionOut.model_validate(q)
