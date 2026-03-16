export interface User {
  id: string;
  upn: string;
  display_name: string;
  is_teacher: boolean;
}

export interface Class {
  id: string;
  name: string;
  school_year: string;
  teacher_id: string;
}

export interface Competency {
  id: string;
  legacy_id: number | null;
  bp_nummer: string | null;
  name: string;
  thema: string | null;
  typ: "einfach" | "niveau";
  is_active: boolean;
  display_order: number;
}

export interface Record {
  competency_id: string;
  achieved: boolean;
  niveau_level: number | null;
  evidence_url: string | null;
  updated_at: string;
}

export interface GradeSummary {
  gesamtpunkte: number;
  max_punkte: number;
  prozent: number;
  note: string;
}

export interface StudentRecordResponse {
  records: Record[];
  grade: GradeSummary;
}

export interface QuestionItem {
  kid: string;
  question_id: string;
  text: string;
}

export interface GeneratedTest {
  id: string;
  student_id: string;
  class_id: string;
  created_at: string;
  pdf_generated_at: string | null;
  pdf_error: string | null;
  competency_ids: string[];
}

export interface Appointment {
  id: string;
  ms_booking_id: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  status: "pending" | "confirmed" | "cancelled";
}
