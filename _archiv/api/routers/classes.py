from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from auth.dependencies import get_current_user, require_teacher
from db.session import get_db
from models.models import Class, ClassEnrollment, User
from schemas.schemas import ClassCreate, ClassOut, EnrollRequest, UserOut

router = APIRouter()


@router.get("", response_model=list[ClassOut])
async def list_classes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.is_teacher:
        result = await db.execute(select(Class).where(Class.teacher_id == user.id))
    else:
        result = await db.execute(
            select(Class)
            .join(ClassEnrollment, ClassEnrollment.class_id == Class.id)
            .where(ClassEnrollment.student_id == user.id)
        )
    return [ClassOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=ClassOut)
async def create_class(
    body: ClassCreate,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    cls = Class(name=body.name, school_year=body.school_year, teacher_id=teacher.id)
    db.add(cls)
    await db.flush()
    return ClassOut.model_validate(cls)


@router.get("/{class_id}/students", response_model=list[UserOut])
async def get_students(
    class_id: str,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
        .where(ClassEnrollment.class_id == class_id)
    )
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.post("/{class_id}/enroll")
async def enroll_student(
    class_id: str,
    body: EnrollRequest,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.upn == body.student_upn))
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found — they must log in first")

    existing = await db.execute(
        select(ClassEnrollment).where(
            ClassEnrollment.class_id == class_id,
            ClassEnrollment.student_id == student.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already enrolled")

    enrollment = ClassEnrollment(class_id=class_id, student_id=student.id)
    db.add(enrollment)
    return {"enrolled": student.id}


@router.delete("/{class_id}/students/{student_id}")
async def remove_student(
    class_id: str,
    student_id: str,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(ClassEnrollment).where(
            ClassEnrollment.class_id == class_id,
            ClassEnrollment.student_id == student_id,
        )
    )
    return {"removed": student_id}
