import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, SmallInteger,
    Text, ForeignKey, CheckConstraint, UniqueConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


def new_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    azure_oid = Column(Text, unique=True, nullable=False)
    upn = Column(Text, unique=True, nullable=False)
    display_name = Column(Text, nullable=False)
    is_teacher = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True))

    classes_taught = relationship("Class", back_populates="teacher")
    enrollments = relationship("ClassEnrollment", back_populates="student")


class Class(Base):
    __tablename__ = "classes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name = Column(Text, nullable=False)
    school_year = Column(Text, nullable=False)
    teacher_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    teacher = relationship("User", back_populates="classes_taught")
    enrollments = relationship("ClassEnrollment", back_populates="class_", cascade="all, delete-orphan")


class ClassEnrollment(Base):
    __tablename__ = "class_enrollments"

    class_id = Column(UUID(as_uuid=False), ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    student_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    class_ = relationship("Class", back_populates="enrollments")
    student = relationship("User", back_populates="enrollments")


class Competency(Base):
    __tablename__ = "competencies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    legacy_id = Column(Integer, unique=True)
    bp_nummer = Column(Text)
    name = Column(Text, nullable=False)
    thema = Column(Text)
    anmerkungen = Column(Text)
    typ = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("typ IN ('einfach', 'niveau')", name="ck_competency_typ"),
    )

    questions = relationship("Question", back_populates="competency", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    competency_id = Column(UUID(as_uuid=False), ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    competency = relationship("Competency", back_populates="questions")


class StudentCompetencyRecord(Base):
    __tablename__ = "student_competency_records"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=False), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    competency_id = Column(UUID(as_uuid=False), ForeignKey("competencies.id"), nullable=False)
    achieved = Column(Boolean, nullable=False, default=False)
    niveau_level = Column(SmallInteger)
    evidence_url = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint("niveau_level BETWEEN 0 AND 3", name="ck_niveau_level"),
        UniqueConstraint("student_id", "class_id", "competency_id", name="uq_scr"),
    )


class GeneratedTest(Base):
    __tablename__ = "generated_tests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=False), ForeignKey("classes.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    pdf_path = Column(Text)
    pdf_generated_at = Column(DateTime(timezone=True))
    pdf_error = Column(Text)
    competency_ids = Column(ARRAY(Text), nullable=False)

    questions = relationship("GeneratedTestQuestion", back_populates="test", cascade="all, delete-orphan")


class GeneratedTestQuestion(Base):
    __tablename__ = "generated_test_questions"

    test_id = Column(UUID(as_uuid=False), ForeignKey("generated_tests.id", ondelete="CASCADE"), primary_key=True)
    competency_id = Column(UUID(as_uuid=False), ForeignKey("competencies.id"), primary_key=True)
    question_id = Column(UUID(as_uuid=False), ForeignKey("questions.id"), nullable=False)
    display_order = Column(SmallInteger, nullable=False)

    test = relationship("GeneratedTest", back_populates="questions")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    ms_booking_id = Column(Text, unique=True)
    ms_booking_service_id = Column(Text)
    scheduled_start = Column(DateTime(timezone=True))
    scheduled_end = Column(DateTime(timezone=True))
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending','confirmed','cancelled')", name="ck_appointment_status"),
    )
