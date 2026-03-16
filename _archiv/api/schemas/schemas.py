from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# --- Users ---

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    upn: str
    display_name: str
    is_teacher: bool


# --- Classes ---

class ClassCreate(BaseModel):
    name: str
    school_year: str


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    school_year: str
    teacher_id: str


class EnrollRequest(BaseModel):
    student_upn: str


# --- Competencies ---

class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    legacy_id: Optional[int]
    bp_nummer: Optional[str]
    name: str
    thema: Optional[str]
    anmerkungen: Optional[str]
    typ: str
    is_active: bool
    display_order: int


class CompetencyPatch(BaseModel):
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    competency_id: str
    text: str
    is_active: bool


class QuestionCreate(BaseModel):
    text: str


# --- Records ---

class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    competency_id: str
    achieved: bool
    niveau_level: Optional[int]
    evidence_url: Optional[str]
    updated_at: datetime


class RecordWrite(BaseModel):
    achieved: Optional[bool] = None
    niveau_level: Optional[int] = None
    evidence_url: Optional[str] = None


class GradeSummary(BaseModel):
    gesamtpunkte: int
    max_punkte: int
    prozent: float
    note: str


class StudentRecordResponse(BaseModel):
    records: list[RecordOut]
    grade: GradeSummary


class ClassSummaryEntry(BaseModel):
    student_id: str
    display_name: str
    records: list[RecordOut]
    grade: GradeSummary


# --- Tests ---

class QuestionItem(BaseModel):
    kid: str
    question_id: str
    text: str


class TestPreviewRequest(BaseModel):
    class_id: str
    competency_ids: list[str]


class TestPreviewResponse(BaseModel):
    questions: list[QuestionItem]


class TestCreateRequest(BaseModel):
    class_id: str
    questions: list[QuestionItem]


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    student_id: str
    class_id: str
    created_at: datetime
    pdf_generated_at: Optional[datetime]
    pdf_error: Optional[str]
    competency_ids: list[str]


# --- Bookings ---

class BookingServiceOut(BaseModel):
    id: str
    display_name: str
    description: Optional[str]
    duration_minutes: int


class BookingSlot(BaseModel):
    start: datetime
    end: datetime
    staff_id: Optional[str]


class BookingCreate(BaseModel):
    service_id: str
    start: datetime
    end: datetime
    staff_id: Optional[str] = None


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ms_booking_id: Optional[str]
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    status: str


# --- Admin Import ---

class ImportResult(BaseModel):
    imported: int
    skipped: int
    warnings: list[str]
