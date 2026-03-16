import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.dependencies import get_current_user
from db.session import get_db
from models.models import Appointment, User
from schemas.schemas import BookingServiceOut, BookingSlot, BookingCreate, AppointmentOut
from services.bookings_service import BookingsService
from config import settings

router = APIRouter()


def _get_service() -> BookingsService:
    return BookingsService()


@router.get("/page-url")
async def get_bookings_page(_user: User = Depends(get_current_user)):
    return {
        "use_api": settings.USE_BOOKINGS_API,
        "page_url": settings.BOOKINGS_PAGE_URL,
    }


@router.get("/services", response_model=list[BookingServiceOut])
async def list_services(
    user: User = Depends(get_current_user),
    service: BookingsService = Depends(_get_service),
):
    if not settings.USE_BOOKINGS_API:
        raise HTTPException(status_code=503, detail="Bookings API disabled; use page_url")
    return await service.list_services()


@router.get("/slots", response_model=list[BookingSlot])
async def get_slots(
    service_id: str,
    user: User = Depends(get_current_user),
    svc: BookingsService = Depends(_get_service),
):
    if not settings.USE_BOOKINGS_API:
        raise HTTPException(status_code=503, detail="Bookings API disabled; use page_url")
    return await svc.get_available_slots(service_id)


@router.post("", response_model=AppointmentOut)
async def create_booking(
    body: BookingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    svc: BookingsService = Depends(_get_service),
):
    if not settings.USE_BOOKINGS_API:
        raise HTTPException(status_code=503, detail="Bookings API disabled; use page_url")

    ms_result = await svc.create_appointment(
        service_id=body.service_id,
        start=body.start,
        end=body.end,
        customer_upn=user.upn,
        customer_name=user.display_name,
    )

    # Find teacher for this booking business
    result = await db.execute(select(User).where(User.is_teacher == True).limit(1))
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(status_code=500, detail="No teacher found")

    appt = Appointment(
        student_id=user.id,
        teacher_id=teacher.id,
        ms_booking_id=ms_result.get("id"),
        ms_booking_service_id=body.service_id,
        scheduled_start=body.start,
        scheduled_end=body.end,
        status="confirmed",
    )
    db.add(appt)
    await db.flush()
    return AppointmentOut.model_validate(appt)


@router.delete("/{appointment_id}")
async def cancel_booking(
    appointment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    svc: BookingsService = Depends(_get_service),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if appt is None:
        raise HTTPException(status_code=404)
    if appt.student_id != user.id and not user.is_teacher:
        raise HTTPException(status_code=403)

    if settings.USE_BOOKINGS_API and appt.ms_booking_id:
        await svc.cancel_appointment(appt.ms_booking_id)

    appt.status = "cancelled"
    return {"cancelled": appointment_id}


@router.get("/me", response_model=list[AppointmentOut])
async def my_appointments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Appointment).where(Appointment.student_id == user.id).order_by(Appointment.scheduled_start)
    )
    return [AppointmentOut.model_validate(a) for a in result.scalars().all()]
