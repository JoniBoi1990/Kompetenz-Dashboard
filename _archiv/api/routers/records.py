from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from datetime import datetime

from auth.dependencies import get_current_user, require_teacher
from db.session import get_db
from models.models import StudentCompetencyRecord, Competency, User, ClassEnrollment
from schemas.schemas import RecordOut, RecordWrite, StudentRecordResponse, GradeSummary, ClassSummaryEntry

router = APIRouter()


def calculate_grade(records: list, all_competencies: list) -> GradeSummary:
    max_punkte = sum(3 if c.typ == "niveau" else 1 for c in all_competencies)
    record_map = {r.competency_id: r for r in records}
    gesamtpunkte = 0

    for c in all_competencies:
        r = record_map.get(c.id)
        if r is None:
            continue
        if c.typ == "einfach":
            gesamtpunkte += 1 if r.achieved else 0
        else:
            gesamtpunkte += (r.niveau_level or 0)

    prozent = (gesamtpunkte / max_punkte * 100) if max_punkte > 0 else 0
    note = (
        "1" if prozent >= 90 else
        "2" if prozent >= 80 else
        "3" if prozent >= 70 else
        "4" if prozent >= 60 else
        "5" if prozent >= 50 else "6"
    )
    return GradeSummary(
        gesamtpunkte=gesamtpunkte,
        max_punkte=max_punkte,
        prozent=round(prozent, 1),
        note=note,
    )


@router.get("/me/{class_id}", response_model=StudentRecordResponse)
async def my_records(
    class_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    records_result = await db.execute(
        select(StudentCompetencyRecord).where(
            StudentCompetencyRecord.student_id == user.id,
            StudentCompetencyRecord.class_id == class_id,
        )
    )
    records = records_result.scalars().all()

    comps_result = await db.execute(select(Competency).where(Competency.is_active == True))
    all_comps = comps_result.scalars().all()

    return StudentRecordResponse(
        records=[RecordOut.model_validate(r) for r in records],
        grade=calculate_grade(records, all_comps),
    )


@router.get("/{class_id}/{student_id}", response_model=StudentRecordResponse)
async def student_records(
    class_id: str,
    student_id: str,
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    records_result = await db.execute(
        select(StudentCompetencyRecord).where(
            StudentCompetencyRecord.student_id == student_id,
            StudentCompetencyRecord.class_id == class_id,
        )
    )
    records = records_result.scalars().all()

    comps_result = await db.execute(select(Competency).where(Competency.is_active == True))
    all_comps = comps_result.scalars().all()

    return StudentRecordResponse(
        records=[RecordOut.model_validate(r) for r in records],
        grade=calculate_grade(records, all_comps),
    )


@router.put("/{class_id}/{student_id}/{competency_id}", response_model=RecordOut)
async def write_record(
    class_id: str,
    student_id: str,
    competency_id: str,
    body: RecordWrite,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    stmt = pg_insert(StudentCompetencyRecord).values(
        id=str(uuid.uuid4()),
        student_id=student_id,
        class_id=class_id,
        competency_id=competency_id,
        achieved=body.achieved if body.achieved is not None else False,
        niveau_level=body.niveau_level,
        evidence_url=body.evidence_url,
        updated_at=datetime.utcnow(),
        updated_by=teacher.id,
    ).on_conflict_do_update(
        constraint="uq_scr",
        set_={
            "achieved": body.achieved if body.achieved is not None else False,
            "niveau_level": body.niveau_level,
            "evidence_url": body.evidence_url,
            "updated_at": datetime.utcnow(),
            "updated_by": teacher.id,
        },
    ).returning(StudentCompetencyRecord)
    result = await db.execute(stmt)
    record = result.scalar_one()
    return RecordOut.model_validate(record)


@router.get("/{class_id}/summary", response_model=list[ClassSummaryEntry])
async def class_summary(
    class_id: str,
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    students_result = await db.execute(
        select(User)
        .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
        .where(ClassEnrollment.class_id == class_id)
    )
    students = students_result.scalars().all()

    comps_result = await db.execute(select(Competency).where(Competency.is_active == True))
    all_comps = comps_result.scalars().all()

    summary = []
    for student in students:
        records_result = await db.execute(
            select(StudentCompetencyRecord).where(
                StudentCompetencyRecord.student_id == student.id,
                StudentCompetencyRecord.class_id == class_id,
            )
        )
        records = records_result.scalars().all()
        summary.append(ClassSummaryEntry(
            student_id=student.id,
            display_name=student.display_name,
            records=[RecordOut.model_validate(r) for r in records],
            grade=calculate_grade(records, all_comps),
        ))

    return summary
