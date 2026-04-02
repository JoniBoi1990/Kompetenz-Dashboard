# CLAUDE.md

Guidance for Claude Code working in this repository.

## Repository Purpose

Kompetenz-Dashboard — Microsoft 365-connected student dashboard for chemistry competency tracking, PDF test generation, and appointment booking.

**Stack:** FastAPI + Jinja2, SQLite (`dashboard.db` via `db.py`), MSAL Python (Azure AD auth only). No Docker, no React, no PostgreSQL. Hosted on Uberspace via plain `uvicorn`.

## Git Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable production branch — deployed on Uberspace |
| `agent-dev` | Development branch for AI agents — DEV_MODE features only |

**⚠️ CRITICAL:**
- **DO NOT merge `agent-dev` → `main` directly.** Merges to `main` are done by the user after review.
- **Agents commit only to `agent-dev`.** Commit format: `agent: <short description>`
- `agent-dev` contains DEV_MODE-only code (test users, test classes, multi-subject support) that must not reach production.

## Service Topology

```
Uberspace (bhof.uber.space)
└── FastAPI (uvicorn main:app, port 8000, systemd user service)
    ├── Jinja2 HTML templates (no npm, no React)
    ├── MSAL Python (Azure AD auth — User.Read only)
    ├── pdf_engine.py (directly imported, synchronous)
    └── db.py → SQLite (dashboard.db) — all app data
        ├── einfach_records, nachweise, active_ids
        ├── test_requests, kompetenzantraege
        └── classes, class_members
```

## Deployment

```bash
# Deploy update (always merge agent-dev → main first)
ssh bhof@larissa.uberspace.de "cd ~/Kompetenz-Dashboard && git pull && systemctl --user restart kompetenz"

# View logs
ssh bhof@larissa.uberspace.de "journalctl --user -u kompetenz -f"
```

## Project Layout

```
Kompetenz-Dashboard/
├── main.py              # FastAPI app + all routes
├── config.py            # Settings via pydantic-settings (.env)
├── auth.py              # MSAL + itsdangerous session cookies
├── db.py                # SQLite persistence layer
├── graph.py             # MS Graph API client (auth only in production)
├── pdf_engine.py        # PDF generation
├── dashboard.db         # SQLite database (auto-created; not in git)
├── convert_csv_to_json.py  # CLI: convert CSV → JSON competency lists
├── onenote_to_backup.py # Standalone: reads OneNote → backup JSON (device flow)
├── grading_scale.json   # Active grading scale (absent = use default preset)
├── static/logo.png      # School logo (place manually, not in git)
├── templates/           # Jinja2 HTML templates
├── kompetenzlisten/     # Class-specific competency lists (JSON)
│   └── CLAUDE.md        # ← ID format spec + checklist for new classes
├── _samples/            # Sample CSV files (not served)
├── _backup/             # Database backups (not in git)
├── grading_scales/      # Uploaded custom grading scale CSVs (auto-created)
├── AGENT_RULES.md       # Rules for AI agents
└── Project_Overview.md  # Non-technical feature overview
```

## Authentication

- **Flow:** Browser → `/login` → MSAL redirect → Azure AD → `/auth/callback` → signed cookie
- **Session:** itsdangerous `URLSafeTimedSerializer`, 8h TTL, httponly + samesite=lax
- **Role detection:** `roles` claim (`"Lehrer"`) or `@lehrer.` in UPN
- **MSAL scopes:** `User.Read` only — do NOT add `openid`, `profile`, `email` (reserved), `GroupMember.Read.All`, or `Sites.ReadWrite.All`

### Student Identity (student_id)

`student_id` in SQLite uses the **UPN** (`preferred_username`, i.e. email), not the Azure AD Object ID (`oid`).

- `auth.py`: `build_user_info()` sets `oid` to the UPN claim
- `main.py`: `DEV_STUDENT_OID = "dev@schule.de"` matches dev login UPN
- Teachers must add students using the exact UPN/email the student uses to log in

## Routes

| Method | Path | Who | Description |
|--------|------|-----|-------------|
| GET | /login | all | Redirect to Azure AD (or dev login form) |
| GET | /auth/callback | — | MSAL callback, sets cookie |
| POST | /logout | session | Clears cookie |
| GET | / | student | Dashboard: score, planning mode, Kompetenzanträge |
| GET | /teacher | teacher | Class overview + pending badges |
| GET | /teacher/class/{id} | teacher | Student list |
| GET | /teacher/student/{id} | teacher | Competency grid + grade + planning mode |
| GET | /teacher/coverage | teacher | Set Unterrichtsstand |
| POST | /teacher/coverage/update | teacher | Save Unterrichtsstand |
| POST | /records/update | teacher | Save einfach record (AJAX) |
| POST | /records/nachweis | teacher | Add niveau Nachweis |
| POST | /records/nachweis/delete | teacher | Delete niveau Nachweis |
| GET | /tests/builder | any | Role-split test form |
| POST | /tests/generate | teacher | Create preview → /tests/preview/{pid} |
| POST | /tests/request | student | Submit test request |
| GET | /tests/pending | teacher | List pending student test requests |
| POST | /tests/confirm/{req_id} | teacher | Create preview from student request |
| GET | /tests/preview/{pid} | teacher | Question-level preview |
| POST | /tests/finalize/{pid} | teacher | Generate PDF, mark request done |
| POST | /antraege/submit | student | Submit competency claim |
| GET | /antraege/pending | teacher | Review pending claims |
| POST | /antraege/accept/{id} | teacher | Accept claim |
| POST | /antraege/reject/{id} | teacher | Reject claim (Begründung required for niveau) |
| GET | /api/competencies/{list_id} | public | `[{id, name, typ}]` — used by onenote_to_backup.py |
| GET | /api/class-students/{class_id} | teacher | AJAX: student list |
| GET | /api/student-competencies | teacher | AJAX: proven IDs |
| GET | /admin/upload | teacher | CSV upload overview |
| GET | /admin/kompetenzen | teacher | Edit/add/delete competencies |
| GET | /admin/questions | teacher | Edit test questions |
| GET | /admin/grading-scale | teacher | Edit grading scale |
| GET | /admin/classes | teacher | List classes |
| GET | /admin/classes/{class_id} | teacher | Class member management |
| GET | /admin/classes/{class_id}/members/migrate | teacher | Student migration (email change) |
| POST | /admin/classes/{class_id}/members/migrate | teacher | Migrate student to new email |

## Competency Data Model

**IDs are strings with type prefix** — see `kompetenzlisten/CLAUDE.md` for full spec.

- Einfach: `"e.901"`, Niveau: `"n.989"` — **never integers**
- Each class is assigned a `competency_list_id` (e.g., `klasse-9-chemie`) → JSON file in `kompetenzlisten/`
- `active_ids` table stores Unterrichtsstand per `(competency_id, class_id)`

## Grade Formula

- `max_punkte` = Σ (3 if niveau else 1) for active competencies
- Einfach: +1 if achieved | Niveau: +niveau_level (0–3)
- `prozent` = gesamtpunkte / max_punkte × 100
- Note from `_GRADING_SCALE` (top-to-bottom, first `prozent >= min_percent` wins)
- **Unterrichtsstand basis** = `active_ids ∪ proven_ids` (self-taught counts)
- Implemented in `main.py:calculate_grade()`

## Grading Scale (`grading_scale.json`)

- `[{"note": "1", "dezimal": 1.0, "min_percent": 100.0}, ...]` sorted descending by `min_percent`
- Note "6" is implicit fallback (not stored)
- Absent → `_default_grading_scale()` reads built-in preset CSV from `_samples/`
- Default preset: `Note-Dezimal-ProzentSchwelleab-Prozentbereichca-2.csv` (50% → 3−4)
- CSV format: `Note,Dezimal,Prozent (Schwelle ab),Prozentbereich (ca.)` — comma-separated UTF-8

## Student Dashboard (`/`)

- Score card: `X von Y Punkten (Z %)` — **no grade letter shown here**
- **Planungsmodus** (client-side JS): interactive checkboxes/dropdowns, live recalculation, grade shown, basis toggle, reset
- Template receives `kompetenzen_json`, `current_state_json`, `active_ids_list`, `proven_ids_list`, `grading_scale_json`

## Kompetenzanträge

Students claim competencies they believe they've proven:
- Einfach: free-text, inline in dashboard; Niveau: evidence URL
- Teacher review at `/antraege/pending`: accept (writes record) or reject (Begründung shown to student)
- Stored via `db.save_kompetenzantrag()` / `db.get_all_kompetenzantraege()`

## Test Generator

**Student view:** no title/class fields; title auto `"Kompetenznachweis Nr. N"`; proven comps disabled; submit → `POST /tests/request` → confirmation + Bookings link.

**Teacher view:** title + student name + "Vorschlag laden" (AJAX); submit → preview → finalize → PDF.

**`_TEST_PREVIEWS`** (in-memory dict): lost on restart. Test requests themselves are persisted in SQLite.

## Templates — Thema Grouping

Einfach competencies grouped by `thema` using Jinja2 `namespace` pattern:
```jinja2
{% set ns = namespace(last_thema=None) %}
{% for k in einfach_kompetenzen %}
  {% if k.thema != ns.last_thema %}{% set ns.last_thema = k.thema %}
    <tr class="thema-header">...</tr>
  {% endif %}
{% endfor %}
```
Interactive views add per-thema Alle/Keine AJAX buttons. `student_detail.html` uses `fetch` on checkbox change (no page reload).

## SQLite Schema (key tables)

**`einfach_records`:** `student_id TEXT`, `competency_id TEXT`, `achieved INTEGER`, `student_name`, `updated_by`, `updated_at`

**`nachweise`:** `id UUID`, `student_id`, `competency_id TEXT`, `niveau_level` (1–3), `evidence_url`, `updated_by`, `updated_at`

**`active_ids`:** `competency_id TEXT`, `class_id TEXT` — PRIMARY KEY `(competency_id, class_id)`

**`test_requests`:** `id`, `student_id`, `student_name`, `title`, `competency_ids` (JSON array), `status` (pending/done), `created_at`

**`kompetenzantraege`:** `id UUID`, `data` (JSON blob)

**`classes`:** `id`, `name`, `grade_level`, `competency_list_id`, `list_source` (system/teacher)

**`class_members`:** `class_id`, `student_id`, `student_name`, `upn` — PK `(class_id, student_id)`

CSV import (`db.import_class_members_csv()`): columns `Name`/`Vorname`+`Nachname`, `UPN`/`E-Mail`/`UserPrincipalName`.

## Student Migration (Email Change)

`Admin → Klassen → [Class] → Mitglieder → "Schüler umziehen"` — transfers all `einfach_records`, `nachweise`, `test_requests`, and class membership to the new email. Implemented in `db.migrate_student()`.

## DEV_MODE

**⚠️ NEVER commit DEV_MODE changes to git** (changes to `_init_dev_db()`, dev login, test classes/students).

`DEV_MODE=true` enables `/dev-login` (no Azure AD). Test users: `anna@schule.de` (Klasse 9), `max@schule.de` (Klasse 10), `lehrer@schule.de`.

## PDF Engine (`pdf_engine.py`)

`create_pdf(questions, name, datum, zusatzinfo)` → `bytes`.
- `questions` = list of `{kid: str, text: str}`
- `zusatzinfo` = title (e.g. `"Kompetenznachweis Nr. 3"`)
- Logo: `static/logo.png` (relative to project root)

## CSV Formats

**ibK (einfach):** `ID;BP-Nummer;Kompetenz;Thema;Anmerkungen` — semikolon UTF-8

**pbK (niveau):** `ID;Nummer;pbk;Möglichkeit1;Möglichkeit2;Möglichkeit3;Hinweise` — semikolon UTF-8

**Testfragen:** Row 0 = competency ID headers (`e.901;e.902;...`), rows 1–N = question variants

## Environment Variables

```
DEV_MODE=false
DOMAIN=bhof.uber.space
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_TENANT_ID=...
SESSION_SECRET=...     # python -c "import secrets; print(secrets.token_hex(32))"
USE_BOOKINGS_API=false
BOOKINGS_PAGE_URL=https://outlook.office.com/book/...
```

## Running Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DEV_MODE=true
uvicorn main:app --reload
# → http://localhost:8000/login
```
