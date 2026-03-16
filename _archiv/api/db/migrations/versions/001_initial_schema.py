"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("azure_oid", sa.Text, unique=True, nullable=False),
        sa.Column("upn", sa.Text, unique=True, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("is_teacher", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "classes",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("school_year", sa.Text, nullable=False),
        sa.Column("teacher_id", sa.Text, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "class_enrollments",
        sa.Column("class_id", sa.Text, sa.ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "competencies",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("legacy_id", sa.Integer, unique=True),
        sa.Column("bp_nummer", sa.Text),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("thema", sa.Text),
        sa.Column("anmerkungen", sa.Text),
        sa.Column("typ", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("typ IN ('einfach', 'niveau')", name="ck_competency_typ"),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("competency_id", sa.Text, sa.ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "student_competency_records",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Text, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competency_id", sa.Text, sa.ForeignKey("competencies.id"), nullable=False),
        sa.Column("achieved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("niveau_level", sa.SmallInteger),
        sa.Column("evidence_url", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Text, sa.ForeignKey("users.id")),
        sa.CheckConstraint("niveau_level BETWEEN 0 AND 3", name="ck_niveau_level"),
        sa.UniqueConstraint("student_id", "class_id", "competency_id", name="uq_scr"),
    )

    op.create_table(
        "generated_tests",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_id", sa.Text, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_id", sa.Text, sa.ForeignKey("classes.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("pdf_path", sa.Text),
        sa.Column("pdf_generated_at", sa.DateTime(timezone=True)),
        sa.Column("pdf_error", sa.Text),
        sa.Column("competency_ids", postgresql.ARRAY(sa.Text), nullable=False),
    )

    op.create_table(
        "generated_test_questions",
        sa.Column("test_id", sa.Text, sa.ForeignKey("generated_tests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("competency_id", sa.Text, sa.ForeignKey("competencies.id"), primary_key=True),
        sa.Column("question_id", sa.Text, sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("display_order", sa.SmallInteger, nullable=False),
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_id", sa.Text, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("teacher_id", sa.Text, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ms_booking_id", sa.Text, unique=True),
        sa.Column("ms_booking_service_id", sa.Text),
        sa.Column("scheduled_start", sa.DateTime(timezone=True)),
        sa.Column("scheduled_end", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','confirmed','cancelled')", name="ck_appointment_status"),
    )

    # Indexes
    op.create_index("idx_scr_student", "student_competency_records", ["student_id", "class_id"])
    op.create_index("idx_scr_class", "student_competency_records", ["class_id"])
    op.create_index("idx_questions_cid", "questions", ["competency_id"])
    op.create_index("idx_tests_student", "generated_tests", ["student_id", "class_id"])


def downgrade():
    op.drop_table("appointments")
    op.drop_table("generated_test_questions")
    op.drop_table("generated_tests")
    op.drop_table("student_competency_records")
    op.drop_table("questions")
    op.drop_table("competencies")
    op.drop_table("class_enrollments")
    op.drop_table("classes")
    op.drop_table("users")
