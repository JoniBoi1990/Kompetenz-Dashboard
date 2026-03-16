import random
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.dependencies import get_current_user, require_teacher
from db.session import get_db
from models.models import GeneratedTest, GeneratedTestQuestion, Question, Competency, User
from schemas.schemas import TestPreviewRequest, TestPreviewResponse, TestCreateRequest, TestOut, QuestionItem
from tasks.pdf_task import generate_pdf_task
from config import settings

router = APIRouter()


async def _sample_questions(competency_ids: list[str], db: AsyncSession) -> list[QuestionItem]:
    items = []
    for comp_id in competency_ids:
        result = await db.execute(
            select(Question).where(
                Question.competency_id == comp_id,
                Question.is_active == True,
            )
        )
        questions = result.scalars().all()
        if not questions:
            comp_result = await db.execute(select(Competency).where(Competency.id == comp_id))
            comp = comp_result.scalar_one_or_none()
            name = comp.name if comp else comp_id
            items.append(QuestionItem(kid=str(comp_id), question_id="", text=f"Keine Frage für: {name}"))
        else:
            q = random.choice(questions)
            items.append(QuestionItem(kid=str(comp_id), question_id=q.id, text=q.text))
    return items


@router.post("/preview", response_model=TestPreviewResponse)
async def preview_test(
    body: TestPreviewRequest,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    questions = await _sample_questions(body.competency_ids, db)
    return TestPreviewResponse(questions=questions)


@router.post("", response_model=TestOut)
async def create_test(
    body: TestCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    test = GeneratedTest(
        student_id=user.id,
        class_id=body.class_id,
        competency_ids=[q.kid for q in body.questions],
    )
    db.add(test)
    await db.flush()

    for i, item in enumerate(body.questions):
        if item.question_id:
            tq = GeneratedTestQuestion(
                test_id=test.id,
                competency_id=item.kid,
                question_id=item.question_id,
                display_order=i,
            )
            db.add(tq)

    await db.flush()
    generate_pdf_task.delay(test.id)
    return TestOut.model_validate(test)


@router.get("/me/{class_id}", response_model=list[TestOut])
async def my_tests(
    class_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedTest).where(
            GeneratedTest.student_id == user.id,
            GeneratedTest.class_id == class_id,
        ).order_by(GeneratedTest.created_at.desc())
    )
    return [TestOut.model_validate(t) for t in result.scalars().all()]


@router.get("/class/{class_id}", response_model=list[TestOut])
async def class_tests(
    class_id: str,
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedTest).where(
            GeneratedTest.class_id == class_id
        ).order_by(GeneratedTest.created_at.desc())
    )
    return [TestOut.model_validate(t) for t in result.scalars().all()]


@router.get("/{test_id}", response_model=TestOut)
async def get_test(
    test_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeneratedTest).where(GeneratedTest.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    if not user.is_teacher and test.student_id != user.id:
        raise HTTPException(status_code=403)
    return TestOut.model_validate(test)


@router.get("/{test_id}/pdf")
async def download_pdf(
    test_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeneratedTest).where(GeneratedTest.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404)
    if not user.is_teacher and test.student_id != user.id:
        raise HTTPException(status_code=403)
    if not test.pdf_path or not Path(test.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not ready yet")
    return FileResponse(test.pdf_path, media_type="application/pdf", filename=f"test_{test_id}.pdf")
