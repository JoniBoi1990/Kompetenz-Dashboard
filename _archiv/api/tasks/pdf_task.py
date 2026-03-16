import asyncio
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from celery_app import celery
from config import settings


@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def generate_pdf_task(self, test_id: str):
    """Celery task: fetch test data from DB, call pdf-worker, save PDF, update DB."""
    asyncio.run(_async_generate(self, test_id))


async def _async_generate(task, test_id: str):
    from db.session import AsyncSessionLocal
    from models.models import GeneratedTest, GeneratedTestQuestion, Question, User, Class

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GeneratedTest)
            .options(selectinload(GeneratedTest.questions))
            .where(GeneratedTest.id == test_id)
        )
        test = result.scalar_one_or_none()
        if test is None:
            return

        student_result = await db.execute(select(User).where(User.id == test.student_id))
        student = student_result.scalar_one()

        class_result = await db.execute(select(Class).where(Class.id == test.class_id))
        cls = class_result.scalar_one()

        # Build question list for pdf-worker
        questions = []
        for tq in sorted(test.questions, key=lambda x: x.display_order):
            q_result = await db.execute(select(Question).where(Question.id == tq.question_id))
            q = q_result.scalar_one_or_none()
            if q:
                questions.append({"kid": tq.competency_id, "text": q.text})

        payload = {
            "student_name": student.display_name,
            "class_name": cls.name,
            "datum": datetime.utcnow().strftime("%d.%m.%Y"),
            "zusatzinfo": cls.school_year,
            "questions": questions,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{settings.PDF_WORKER_URL}/generate", json=payload)
                resp.raise_for_status()
                pdf_bytes = resp.content

            pdf_path = Path(settings.PDF_STORAGE_PATH) / f"{test_id}.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf_bytes)

            test.pdf_path = str(pdf_path)
            test.pdf_generated_at = datetime.utcnow()
            test.pdf_error = None
        except Exception as exc:
            test.pdf_error = str(exc)
            await db.commit()
            raise task.retry(exc=exc)

        await db.commit()
