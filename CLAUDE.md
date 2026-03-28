# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

Kompetenz-Dashboard — a Microsoft 365-connected student dashboard for chemistry competency tracking, personalized PDF test generation, and appointment booking.

**Architecture decision (2026-03):** The original Docker Compose + PostgreSQL plan was replaced with a lean FastAPI + Jinja2 app. No Docker, no React. Hosted on Uberspace via plain `uvicorn`.

**Data layer decision (2026-03):** Microsoft SharePoint Lists replaced by SQLite (`dashboard.db` via `db.py`). Azure AD is used for authentication only (`User.Read` scope). Classes and students are managed directly in SQLite instead of being fetched from MS Graph.

## Git Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable production branch — deployed on Uberspace |
| `agent-dev` | Development branch for AI agents — **DEV_MODE features only** |

**⚠️ CRITICAL: `agent-dev` contains DEV_MODE-only code!**

The `agent-dev` branch has features that only work with `DEV_MODE=true`:
- Multiple test users (Anna, Max, Lehrer)
- Test classes (9a, 10a) with sample data
- Class-specific competency lists (Klasse 9, 10)
- **Multi-subject support** (Chemie, Physik, etc.) — students can have multiple subjects per class
- CSV upload workflow for competency lists
- Class-specific active_ids (Unterrichtsstand) per subject

**DO NOT merge `agent-dev` → `main` directly!** The production app uses Azure AD and a different data model.

**Agents must only commit to `agent-dev`.** Merges to `main` are done by the user after careful review.

Commit format: `agent: <short description>`

## Service Topology

```
Uberspace (larissa.uberspace.de → bhof.uber.space)
└── FastAPI (uvicorn main:app, port 8000, systemd user service)
    ├── Jinja2 HTML templates (no npm, no React)
    ├── MSAL Python (Azure AD auth — User.Read only)
    ├── pdf_engine.py (directly imported, synchronous)
    ├── db.py → SQLite (dashboard.db) — all app data
    │   ├── einfach_records, nachweise
    │   ├── active_ids (Unterrichtsstand per class_subject)
    │   ├── test_requests, kompetenzantraege
    │   ├── classes, class_members
    │   ├── class_subjects, student_subjects (multi-subject support)
    └── Azure AD → identity + roles (Lehrer / Schüler) only
```

**Removed entirely:** Docker, PostgreSQL, Redis, Celery, pdf-worker microservice, React SPA, nginx, Traefik.

Old files are archived in `_archiv/`.

## Deployment

**Production URL:** https://bhof.uber.space
**Server:** bhof@larissa.uberspace.de
**Service:** systemd user service `kompetenz`

```bash
# Deploy update
ssh bhof@larissa.uberspace.de "cd ~/Kompetenz-Dashboard && git pull && systemctl --user restart kompetenz"

# View logs
ssh bhof@larissa.uberspace.de "journalctl --user -u kompetenz -f"

# Service status
ssh bhof@larissa.uberspace.de "systemctl --user status kompetenz"
```

The server tracks the `main` branch. Always merge `agent-dev` → `main` before deploying.

## Project Layout

```
Kompetenz-Dashboard/
├── main.py              # FastAPI app + all routes
├── config.py            # Settings via pydantic-settings (.env)
├── auth.py              # MSAL + itsdangerous session cookies
├── db.py                # SQLite persistence layer (replaces MS Lists)
├── graph.py             # MS Graph API client (kept; auth only in production)
├── pdf_engine.py        # PDF generation (ported from app5.py, bug-fixed)
├── dashboard.db         # SQLite database (auto-created; not in git)
├── convert_csv_to_json.py  # CLI tool to convert CSV to JSON competency lists
├── onenote_to_backup.py # Standalone: reads OneNote class notebook → backup JSON (device flow auth)
├── grading_scale.json   # Active grading scale (absent = use default preset)
├── static/
│   ├── logo.png         # School logo (place here manually, not in git)
│   └── style.css
├── templates/           # Jinja2 HTML templates
│   ├── base.html
│   ├── dashboard.html        # Student view: score + planning mode + Kompetenzanträge + subject selector
│   ├── teacher.html          # Teacher class overview + pending badges
│   ├── class_detail.html
│   ├── student_detail.html   # Now with subject selector for multi-subject support
│   ├── test_builder.html     # Role-split: student request / teacher generate + subject selector
│   ├── test_preview.html     # Teacher: question-level preview before PDF download
│   ├── pending_tests.html    # Teacher: review + confirm student test requests
│   ├── antraege_pending.html # Teacher: review student competency claims
│   ├── test_request_sent.html
│   ├── grade_calculator.html # Now with subject/class selector
│   ├── coverage.html         # Now with subject selector for multi-subject classes
│   ├── bookings.html
│   ├── upload.html               # CSV upload page (ibK, pbK, Testfragen)
│   ├── teacher_competency_lists.html  # Manage class-subject assignments
│   ├── admin_kompetenzen.html    # Edit/add/delete competencies
│   ├── admin_questions.html      # Edit test questions per competency
│   ├── admin_grading_scale.html  # Edit grading scale + upload/preset selection
│   ├── admin_classes.html        # Manage classes (add/delete)
│   └── admin_class_members.html  # Manage class members (add/delete/CSV import)
├── kompetenzlisten/     # Class-specific competency lists (JSON format)
│   ├── klasse-9-chemie.json              # Klasse 9 Chemie competencies
│   ├── klasse-9-chemie-questions.json    # Klasse 9 Chemie test questions
│   ├── klasse-10-chemie.json             # Klasse 10 Chemie competencies
│   └── klasse-10-chemie-questions.json   # Klasse 10 Chemie test questions
├── _samples/            # Sample CSV files (not served)
│   ├── einfach_9_alle.csv
│   ├── Niveau_9_alle.csv
│   ├── einfach_10_alle.csv
│   ├── vorlage-kompetenzen.csv
│   ├── vorlage-fragen.csv
│   ├── Note-Dezimal-ProzentSchwelleab-Prozentbereichca-2.csv   # default preset (50%→3−4)
│   └── Note-Dezimal-ProzentSchwelleab-Prozentbereichca.csv    # alt preset (50%→3−)
├── _archiv/             # Archived old files
│   ├── docs/
│   └── migration-20260319/   # Old kompetenzen.json, questions.json
├── _backup/             # Database backups (not in git)
├── grading_scales/      # Uploaded custom grading scale CSVs (auto-created, not in git)
├── requirements.txt
├── .env.example
├── Procfile             # uvicorn main:app --host 0.0.0.0 --port $PORT
├── AGENT_RULES.md       # Rules for AI agents working in this repo
├── Project_Overview.md  # Non-technical feature overview
└── _archiv/             # Old Docker/React/PostgreSQL code (do not edit)
```

## Authentication

- **Flow:** Browser → `GET /login` → MSAL redirect → Azure AD → `GET /auth/callback` → code exchange → signed cookie (itsdangerous)
- **Session:** itsdangerous `URLSafeTimedSerializer`, 8h TTL, httponly + samesite=lax
- **Role detection:** `roles` claim (`"Lehrer"`) or `@lehrer.` in UPN
- **Cookie name:** `session`
- **MSAL scopes:** `User.Read` only — do NOT add `openid`, `profile`, `email` (reserved), `GroupMember.Read.All`, or `Sites.ReadWrite.All` (no longer needed)
- **DEV_MODE:** `DEV_MODE=true` in `.env` enables a fake login form (`/dev-login`) — no Azure AD needed

### Student Identity (student_id)

**Important:** The `student_id` stored in SQLite (`einfach_records`, `nachweise`, `class_members`, etc.) uses the **UPN** (`preferred_username`, i.e. the user's email) rather than the Azure AD Object ID (`oid`).

**Rationale:** Teachers add students via email/UPN in the admin UI. Using UPN as the primary key ensures that teacher-created records match the student's login identity without requiring an OID-to-UPN mapping table.

**Implementation:**
- `auth.py`: `build_user_info()` sets `oid` to the UPN claim
- `main.py`: `DEV_STUDENT_OID = "dev@schule.de"` matches the dev login UPN
- Teachers must add students using the exact UPN/email the student uses to log in

## Routes

| Method | Path | Who | Description |
|--------|------|-----|-------------|
| GET | /login | all | Redirect to Azure AD (or dev login form) |
| GET | /auth/callback | — | MSAL callback, sets cookie |
| POST | /logout | session | Clears cookie |
| GET | /auth/me | session | JSON user info |
| GET | / | student | Dashboard: score (no grade), planning mode, Kompetenzanträge |
| GET | /teacher | teacher | Class overview + pending test + antrag count badges |
| GET | /teacher/class/{id} | teacher | Student list (SQLite) |
| GET | /teacher/student/{id} | teacher | Competency grid + grade + **planning mode** |
| GET | /teacher/coverage | teacher | Set which competencies are in Unterrichtsstand |
| POST | /teacher/coverage/update | teacher | Save Unterrichtsstand |
| POST | /records/update | teacher | Save einfach record → SQLite (also accepts AJAX) |
| POST | /records/nachweis | teacher | Add niveau Nachweis → SQLite |
| POST | /records/nachweis/delete | teacher | Delete niveau Nachweis |
| POST | /tests/delete/{req_id} | teacher | Delete test request |
| GET | /tests/builder | any | Role-split test form |
| POST | /tests/generate | teacher | Create preview (→ redirect to /tests/preview/{pid}) |
| POST | /tests/request | student | Submit test request (stored, no PDF yet) |
| GET | /tests/pending | teacher | List pending student test requests |
| POST | /tests/confirm/{req_id} | teacher | Create preview from student request |
| GET | /tests/preview/{pid} | teacher | Question-level preview with per-question dropdowns |
| POST | /tests/finalize/{pid} | teacher | Generate PDF from preview, mark request done |
| POST | /antraege/submit | student | Submit competency claim |
| GET | /antraege/pending | teacher | Review pending competency claims |
| POST | /antraege/accept/{id} | teacher | Accept claim (writes record/nachweis) |
| POST | /antraege/reject/{id} | teacher | Reject claim (with Begründung for niveau) |
| GET | /api/competencies/{list_id} | public | Returns [{id, name, typ}] for a system or teacher list — used by onenote_to_backup.py |
| GET | /api/class-students/{class_id} | teacher | AJAX: student list for a class |
| GET | /api/student-competencies | teacher | AJAX: proven IDs for student name lookup |
| GET | /grades/calculator | any | ~~Grade calculator~~ (deprecated for teachers — use planning mode in student detail) |
| POST | /grades/calculate | any | ~~Compute grade from form~~ |
| GET | /bookings | any | Bookings link page |
| GET | /admin/upload | teacher | CSV upload overview + status |
| POST | /admin/upload/kompetenzen | teacher | Import ibK CSV → kompetenzen.json |
| POST | /admin/upload/niveau | teacher | Import pbK CSV → kompetenzen.json |
| POST | /admin/upload/questions | teacher | Import Testfragen CSV → questions.json |
| GET | /admin/kompetenzen | teacher | Edit/add/delete all competencies |
| POST | /admin/kompetenzen/save | teacher | Save edits → kompetenzen.json |
| POST | /admin/kompetenzen/add | teacher | Add new competency |
| POST | /admin/kompetenzen/delete | teacher | Delete competency by ID |
| GET | /admin/questions | teacher | Edit questions per competency |
| POST | /admin/questions/add | teacher | Add question variant |
| POST | /admin/questions/delete | teacher | Delete question variant |
| GET | /admin/grading-scale | teacher | Edit grading scale + upload/preset selection |
| POST | /admin/grading-scale/save | teacher | Save threshold edits → grading_scale.json |
| POST | /admin/grading-scale/reset | teacher | Delete grading_scale.json → revert to default preset |
| POST | /admin/grading-scale/upload | teacher | Upload custom scale CSV → grading_scales/ |
| GET | /admin/classes | teacher | List classes (SQLite) |
| POST | /admin/classes/add | teacher | Add new class |
| POST | /admin/classes/delete | teacher | Delete class + all members |
| GET | /admin/classes/{class_id} | teacher | Class member management page |
| POST | /admin/classes/{class_id}/members/add | teacher | Add student to class |
| POST | /admin/classes/{class_id}/members/delete | teacher | Remove student from class |
| POST | /admin/classes/{class_id}/members/import | teacher | Bulk import members from CSV |
| GET | /admin/classes/{class_id}/members/migrate | teacher | Student migration page (email change) |
| POST | /admin/classes/{class_id}/members/migrate | teacher | Migrate student to new email/ID |

## Navigation (role-dependent)

**Teacher:** Klassen | Unterrichtsstand | Testanfragen | Kompetenzanträge | Testgenerator | Notenschlüssel | Klassen verwalten

**Student:** Meine Kompetenzen | Nachweis anfordern

**Note:** "Listen verwalten" was removed. Competency lists are now managed as JSON files in `kompetenzlisten/` directory (system lists) or uploaded by teachers per class.

## Competency Data Model (Grade-Level Based with Type Prefix)

**⚠️ CRITICAL: ID Format changed in 2026-03**

Old format (deprecated): Integer IDs like `901`, `1001`
New format: **String IDs with type prefix** — `"e.901"` (einfach), `"n.989"` (niveau)

### File Structure

```
kompetenzlisten/
├── klasse-9-chemie.json              # Klasse 9: IDs e.901-e.988, n.989-n.1021
├── klasse-9-chemie-questions.json    # Questions for Klasse 9
├── klasse-10-chemie.json             # Klasse 10: IDs e.1001-e.1070, n.1071-n.1103
└── klasse-10-chemie-questions.json   # Questions for Klasse 10
```

### ID Format Specification

**Format:** `{type}.{grade}{sequence:02d}`

| Type | Prefix | Example | Meaning |
|------|--------|---------|---------|
| Einfach | `e.` | `e.901` | Klasse 9, Einfach #01 |
| Niveau | `n.` | `n.989` | Klasse 9, Niveau #01 |

**Pattern:**
- Klasse 9 Einfach: `e.901` - `e.988` (88 competencies)
- Klasse 9 Niveau: `n.989` - `n.1021` (33 competencies)
- Klasse 10 Einfach: `e.1001` - `e.1070` (70 competencies)
- Klasse 10 Niveau: `n.1071` - `n.1103` (33 competencies)

**Why this format:**
1. **No collisions** between Einfach and Niveau (can both have #01)
2. **Human readable** — see type and grade at a glance
3. **Sortable** — alphabetical sort works correctly
4. **Extensible** — add new types (e.g., `p.` for projects) easily

### JSON Entry Structure

```json
{
  "id": "e.901",          // String! Format: "e.{grade}{seq}" or "n.{grade}{seq}"
  "typ": "einfach",       // "einfach" or "niveau" (must match prefix)
  "name": "...",
  "thema": 1,             // Integer 1–10 or null
  "anmerkungen": ""
}
```

### Database Schema (SQLite)

**competency_id columns are TEXT (not INTEGER):**

```sql
-- active_ids (Unterrichtsstand)
CREATE TABLE active_ids (
    competency_id TEXT NOT NULL,  -- e.g., "e.901", "n.989"
    class_id TEXT,
    PRIMARY KEY (competency_id, class_id)
);

-- einfach_records
CREATE TABLE einfach_records (
    student_id TEXT NOT NULL,
    competency_id TEXT NOT NULL,  -- e.g., "e.901"
    achieved INTEGER DEFAULT 0,
    ...
);

-- nachweise (niveau)
CREATE TABLE nachweise (
    student_id TEXT NOT NULL,
    competency_id TEXT NOT NULL,  -- e.g., "n.989"
    niveau_level INTEGER,
    ...
);
```

### Adding a New Class (Checklist)

**Prerequisites:** Decide on grade level (e.g., 11) and subject (e.g., chemie)

**Step 1: Create JSON files**

```bash
# Create empty structure
convert_csv_to_json.py --grade 11 --subject chemie \
  --einfach-csv einfach_11.csv \
  --niveau-csv niveau_11.csv \
  --output-dir kompetenzlisten/
```

This creates:
- `klasse-11-chemie.json` (IDs: e.1101, e.1102, ... n.1190, ...)
- `klasse-11-chemie-questions.json`

**Step 2: Verify ID format in JSON**

```bash
python3 -c "
import json
with open('kompetenzlisten/klasse-11-chemie.json') as f:
    data = json.load(f)
    for c in data['competencies'][:5]:
        print(f\"  {c['id']} ({c['typ']})\")
"
# Should show: e.1101 (einfach), e.1102 (einfach), ...
```

**Step 3: Add class to database**

Via web UI: `Admin → Klassen verwalten → Neue Klasse`

⚠️ **Wichtig:** Nach dem Anlegen der Klasse muss im Admin-UI eine Kompetenzliste zugewiesen werden:
- `Admin → Klassen verwalten → [Klasse anklicken] → Kompetenzliste zuweisen`
- Wähle z.B. "klasse-9-chemie" für Klasse 9 Chemie

Ohne zugewiesene Liste funktioniert der Unterrichtsstand nicht korrekt!

Or SQL:
```sql
INSERT INTO classes (id, name, grade_level, 
                     einfach_list_id, einfach_list_source,
                     niveau_list_id, niveau_list_source)
VALUES ('klasse-11-chemie-2026', '11a Chemie', 11,
        'klasse-11-chemie', 'system',
        'klasse-11-chemie', 'system');
```

**Step 4: Assign students to class**

Via web UI or SQL:
```sql
INSERT INTO class_members (class_id, student_id, student_name, upn)
VALUES ('klasse-11-chemie-2026', 'max@schule.de', 'Max Mustermann', 'max@schule.de');
```

**Step 5: Set Unterrichtsstand (optional)**

Via web UI: `Unterrichtsstand → Klasse 11a auswählen → Kompetenzen markieren → Speichern`

**⚠️ Common Pitfalls:**

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Integer IDs in JSON | Parse errors, "invalid literal" | Convert to strings: `"e.1101"` |
| Missing type prefix | ID collisions between Einfach/Niveau | Add `e.` or `n.` prefix |
| Wrong sequence padding | `e.1101` vs `e.111` | Always use 2-digit sequence: `e.{grade}{seq:02d}` |
| Database still has INTEGER column | "datatype mismatch" | Run migration or recreate tables |
| **Missing competency_list_id** | Unterrichtsstand zeigt 0 Kompetenzen trotz gespeicherter active_ids | Im Admin-UI Kompetenzliste zuweisen |

### Loading Competency Lists

```python
# Load a specific list
einfach_list, niveau_list, active_ids, class_id = _get_student_competencies(student_id)

# Returns separate lists for einfach and niveau
# active_ids: Set of strings like {"e.1101", "e.1102", "n.1190"}
```

### Code Changes Required When Adding Classes

**If IDs follow the pattern: NONE** ✓

The code automatically:
- Parses `e.{grade}{seq}` format
- Loads correct lists based on class assignment
- Filters active_ids by type prefix
- Renders templates with string IDs

**Only modify if:**
- Adding a new competency type (not "einfach" or "niveau")
- Changing the ID format entirely
- Adding metadata fields to competencies

### Critical Code Paths (Handle with Care)

These functions are sensitive to ID format changes:

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `_parse_csv_competencies` | `main.py` | ~815 | CSV → JSON conversion with ID generation |
| `_get_student_competencies` | `main.py` | ~491 | Loads separate einfach/niveau lists |
| `teacher_coverage` | `main.py` | ~1290 | Unterrichtsstand page |
| `teacher_coverage_update` | `main.py` | ~1345 | Saves active_ids (no int() conversion!) |
| `test_builder` | `main.py` | ~1364 | Test generator |
| `api_student_competencies` | `main.py` | ~1600 | AJAX endpoint for proven IDs |
| `get_active_ids` | `db.py` | ~213 | Returns Set[str] of IDs |
| `set_active_ids` | `db.py` | ~231 | Saves Set[str] to database |
| `upsert_einfach` | `db.py` | ~261 | Records einfach achievement |
| `add_nachweis` | `db.py` | ~307 | Records niveau evidence |

**Template files with ID handling:**
- `templates/coverage.html` — Checkbox values, `k.id in active_ids`
- `templates/test_builder.html` — Student lookup, `parseInt()` removed
- `templates/dashboard.html` — Planning mode, JSON payloads
- `templates/student_detail.html` — Teacher view, form submissions

**⚠️ Common bug pattern:**
```python
# WRONG — breaks with string IDs:
ids = {int(v) for k, v in form.multi_items() if k == "active_id"}

# CORRECT:
ids = {v for k, v in form.multi_items() if k == "active_id"}
```

## Test Questions (`{list}-questions.json`)

```json
{
  "e.901": ["Nenne die Grundbausteine...", "Beschreibe den Aufbau..."],
  "e.902": ["Frage 1...", "Frage 2..."],
  "n.989": ["Niveau-Frage..."]
}
```

- **Keys are competency IDs as strings** with type prefix: `"e.901"`, `"n.989"`
- Fallback when a key is missing or file absent: competency name is used as the single question.
- **CSV format:** 
  - Row 0 = competency IDs (column headers) — must include type prefix: `e.901;e.902;n.989`
  - Rows 1–N = question variants
  - Semikolon-separated, UTF-8
  - Empty cells are skipped

**Example CSV for Klasse 11:**
```csv
e.1101;e.1102;e.1103;n.1190;n.1191
"Was ist...?";"Erkläre...";"Nenne...";"Beweise...";"Analysiere..."
"Definiere...";"Beschreibe...";"Liste...";"Vergleiche...";"Diskutiere..."
```

## Student Dashboard (`/`)

- **Persistent score card:** shows `X von Y Punkten (Z %)` — **no grade letter** — filtered by Unterrichtsstand if active
- **Unterrichtsstand basis** includes both active_ids AND competencies the student has already proven (so self-taught competencies count toward the grade)
- **Planungsmodus** (toggle, client-side JS only): interactive checkboxes/dropdowns, live score recalculation, grade letter shown here, basis toggle (Unterrichtsstand / Ganzes Schuljahr), reset button
- Template receives `kompetenzen_json`, `current_state_json`, `active_ids_list`, `proven_ids_list`, `grading_scale_json` for JS
- Template also receives `pending_antraege_by_comp`, `rejected_niveau_antraege_by_comp`, `antrag_ok` for Kompetenzanträge UI
- Competency ID shown in all tables (muted, small)

## Kompetenzanträge (student competency claims)

Students can submit claims for competencies they believe they have already demonstrated:
- **Einfach:** free-text description (hint: max 7 days old), form inline in dashboard read-only table
- **Niveau:** evidence URL (OneDrive, OneNote etc.), form inline in dashboard niveau table
- Pending antrag → badge "Antrag ausstehend" replaces the form
- Rejected niveau antrag → rejection reason shown above re-submit form

Teacher review at `GET /antraege/pending`:
- Accept einfach → writes `achieved=True` to competency record
- Accept niveau → teacher selects level 1–3, writes nachweis entry
- Reject niveau → Begründung required, shown to student on next dashboard load

Data stored in SQLite via `db.save_kompetenzantrag()` / `db.get_all_kompetenzantraege()` — persisted across restarts.

## Test Generator: Role-Split Behaviour

### Student view (`GET /tests/builder` when not teacher)
- No title / class / name text fields — name from `user.display_name`
- Title auto-set to `"Kompetenznachweis Nr. N"` (sequential per student)
- Already-proven `einfach` competencies: `disabled` checkbox, greyed row
- Competencies beyond Unterrichtsstand: marked `↑ voraus`, still selectable
- Default checked: active_ids that are not yet proven
- Submit → `POST /tests/request` → confirmation page with Bookings link
- Backend re-validates and strips proven IDs from submission

### Teacher view (`GET /tests/builder` when teacher)
- Title input, student name input + **"Vorschlag laden"** button (AJAX → `/api/student-competencies`)
- Submit → `POST /tests/generate` → redirect to `/tests/preview/{pid}`

### Preview + finalize (`/tests/preview/{pid}`)
- Shows one row per competency with a dropdown of question variants (if >1 exists)
- Teacher can swap questions before downloading
- `POST /tests/finalize/{pid}` generates PDF, marks linked request as `done`, deletes preview from store

### Student test request workflow
1. Student submits → stored in SQLite (`db.save_test_request()`); confirmation page shows Bookings link
2. Teacher sees count badge on `/teacher`
3. `GET /tests/pending`: cards per request with editable checkboxes
4. `POST /tests/confirm/{req_id}` → preview → `POST /tests/finalize/{pid}` → PDF
5. **Note:** `_TEST_PREVIEWS` (in-progress previews) is in-memory only — lost on restart. Test requests themselves are persisted in SQLite.

## Thema Grouping in Templates

Einfach competencies are grouped by `thema` in all tables. The grouping uses the Jinja2 `namespace` pattern:
```jinja2
{% set ns = namespace(last_thema=None) %}
{% for k in einfach_kompetenzen %}
  {% if k.thema != ns.last_thema %}{% set ns.last_thema = k.thema %}
    <tr class="thema-header"><td colspan="N">Thema {{ k.thema or "–" }} ...</td></tr>
  {% endif %}
  <tr data-thema="{{ k.thema or 0 }}">...</tr>
{% endfor %}
```
Interactive views (coverage, test_builder teacher, grade_calculator, student_detail) add per-thema Alle/Keine buttons with AJAX. Read-only views (dashboard) show headers only.

## Student Detail — AJAX Checkbox + Bulk Thema

`student_detail.html` uses `fetch` to POST `/records/update` on checkbox change — no page reload, no scroll jump. The row flashes green on success, reverts + flashes red on error.

`setThema(thema, state)` bulk-sets all checkboxes for a thema group via the same AJAX helper, one request per checkbox that needs to change.

## Data: SQLite Database (`db.py`)

All app data is stored in `dashboard.db` (SQLite, created automatically). `db.init_db()` creates tables on startup.

### `einfach_records`

| Column | Type | Notes |
|--------|------|-------|
| student_id | TEXT PK | Azure AD object ID |
| competency_id | INTEGER PK | Competency ID |
| student_name | TEXT | Display name (cached) |
| achieved | INTEGER | 0 or 1 |
| updated_by | TEXT | Teacher UPN |
| updated_at | TEXT | ISO timestamp |

### `nachweise`

Each row is one niveau proof attempt: `id` (UUID), `student_id`, `competency_id`, `niveau_level` (1–3), `evidence_url`, `evidence_name`, `updated_by`, `updated_at`.

### `active_ids`

`competency_id`, `class_id` (nullable) — the current Unterrichtsstand set.

- If `class_id` is set: class-specific active IDs
- If `class_id` is NULL: global active IDs (backward compatibility)

### `test_requests`

`id`, `student_id`, `student_name`, `title`, `competency_ids` (JSON array), `status` (`pending`/`done`), `created_at`.

### `kompetenzantraege`

`id` (UUID), `data` (JSON blob) — full antrag dict stored as JSON.

### `classes` + `class_members`

`classes`: `id`, `name`, `description`, `grade_level` (9, 10, etc.), `competency_list_id`, `list_source` ("system" or "teacher").
`class_members`: `class_id`, `student_id`, `student_name`, `upn`. Primary key is `(class_id, student_id)`.

**CSV import** (`db.import_class_members_csv()`): columns `Name` (or `Vorname`+`Nachname`), `UPN` (or `E-Mail` or `UserPrincipalName`).

**Grade-level based competency lists:** Each class is assigned a competency list (e.g., `klasse-9-chemie`, `klasse-10-chemie`). Students only see competencies from their class's list. The lists are stored as JSON files in `kompetenzlisten/` directory.

## DEV_MODE (Local Testing Only — Do Not Commit)

`DEV_MODE=true` enables fake login (`/dev-login`) — no Azure AD needed. All data goes into the same SQLite `dashboard.db`.

**⚠️ NEVER commit DEV_MODE changes to git.** This includes:
- Changes to `_init_dev_db()`
- Dev login page modifications
- Test classes or test students
- Sample data population

### Dev Mode Users
- **Teacher:** `lehrer@schule.de`
- **Student Klasse 9:** `anna@schule.de` (Anna Beispiel)
- **Student Klasse 10:** `max@schule.de` (Max Mustermann)

### Pre-populated on first startup
Via `_init_dev_db()` (skipped if data exists):
- **Klasse 9:** `9a (Dev)` with Anna Beispiel, using `klasse-9-chemie.json`
- **Klasse 10:** `10a (Dev)` with Max Mustermann, using `klasse-10-chemie.json`
- `active_ids`: class-specific Unterrichtsstand per class
- Sample achievements for both students

**`_TEST_PREVIEWS`** (dict in `main.py`): in-memory only, lost on restart. Acceptable — previews are short-lived.

## Grade Formula

- `max_punkte` = Σ (3 if typ == "niveau" else 1) for active competencies
- `einfach`: +1 if achieved
- `niveau`: + niveau_level (0–3)
- `prozent` = gesamtpunkte / max_punkte × 100
- Note determined by `_GRADING_SCALE` (see below)
- Implemented in `main.py:calculate_grade(competencies=...)` — pass filtered list for Unterrichtsstand basis

**Unterrichtsstand basis** = `active_ids ∪ proven_ids` (proven = achieved einfach or niveau_level > 0). Students who self-teach beyond the Unterrichtsstand receive credit.

## Grading Scale (`grading_scale.json`)

- Stored as `[{"note": "1", "dezimal": 1.0, "min_percent": 100.0}, ...]` sorted descending by `min_percent`
- Note "6" is the implicit fallback (not stored); anything below the last threshold → "6"
- Note strings use the school's +/− notation: `"1"`, `"1−"`, `"1−2"`, `"2+"`, ..., `"5−6"`
- `calculate_grade()` iterates the scale top-to-bottom; first entry where `prozent >= min_percent` wins
- `_reload_grading_scale()` loads `grading_scale.json` if present, otherwise calls `_default_grading_scale()` (reads the default preset CSV)

### Built-in presets (in `_samples/`)

| File | 50% → Note | Description |
|------|-----------|-------------|
| `Note-Dezimal-ProzentSchwelleab-Prozentbereichca-2.csv` | 3−4 | **Default** |
| `Note-Dezimal-ProzentSchwelleab-Prozentbereichca.csv` | 3− | Stricter |

### CSV format for grading scale
Comma-separated, UTF-8, headers: `Note,Dezimal,Prozent (Schwelle ab),Prozentbereich (ca.)`. Row with `Dezimal >= 6.0` is the "6" catch-all and is excluded from the array.

### Uploaded presets
Saved to `grading_scales/` named after the note at 50%: `Note_3-4.csv`, `Note_3-4_v2.csv`, etc. (unicode minus → ASCII hyphen in filename). Appear as additional preset buttons on the admin page alongside built-ins.

### Admin page (`/admin/grading-scale`)
- Upload form at top (same CSV format as built-in presets)
- Preset buttons (built-ins + uploaded files): clicking fills thresholds without saving
- Editable table with live "Bereich (ca.)" column updated by JS
- "Speichern" → writes `grading_scale.json`; "Auf Standard zurücksetzen" → deletes it

## PDF Engine (`pdf_engine.py`)

Ported from `app5.py` with two bug fixes:
1. `draw_text_wrapped()` — added `return y` (was missing)
2. `format_chemical_formula()` — `re.finditer()` instead of `str.find()` for repeated tokens

`create_pdf(questions, name, datum, zusatzinfo)` returns `bytes`.
- `questions` = list of `{kid: str, text: str}`
- `zusatzinfo` carries the title (e.g. `"Kompetenznachweis Nr. 3"`)
- Logo: `static/logo.png` (relative to project root)

## CSV Formats

### ibK (einfach competencies)
`ID;BP-Nummer;Kompetenz;Thema;Anmerkungen` — semikolon, UTF-8. `BP-Nummer` stored internally as `bp_nummer`, never shown in UI. Merged by ID into `kompetenzen.json`.

### pbK (niveau competencies)
`ID;Nummer;pbk;Möglichkeit1;Möglichkeit2;Möglichkeit3;Hinweise zu den Kriterien` — semikolon, UTF-8. `Nummer` = bp_nummer (internal). Merged by `bp_nummer` first, then by name match. `Möglichkeit1–3` stored as `moeglichkeiten` list, editable in `/admin/kompetenzen`.

### Testfragen
Row 0 = competency IDs (column headers). Rows 1–N = question variants. Empty cells skipped. Stored in `questions.json` as `{comp_id_str: [question, ...]}`.

### Notenschlüssel
`Note,Dezimal,Prozent (Schwelle ab),Prozentbereich (ca.)` — comma-separated, UTF-8. See Grading Scale section above.

## Environment Variables (.env)

```
DEV_MODE=false                  # true = fake login, SQLite pre-populated with sample data
DOMAIN=bhof.uber.space          # or localhost:8000 for local dev
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_TENANT_ID=...
SESSION_SECRET=...              # python -c "import secrets; print(secrets.token_hex(32))"
USE_BOOKINGS_API=false
BOOKINGS_BUSINESS_ID=
BOOKINGS_PAGE_URL=https://outlook.office.com/book/Birklehof3@birklehof.de/
# SHAREPOINT_SITE_ID no longer required (data is in SQLite)
```

## Running Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DEV_MODE=true for local dev (see warning below)
uvicorn main:app --reload
# → http://localhost:8000/login
```

**⚠️ DEV_MODE Warning:** When `DEV_MODE=true`, the app shows a fake login page with test users (Anna, Max, Lehrer). This is convenient for local development but **must never be committed to git**. Always set `DEV_MODE=false` before committing.

## Grade-Level Based Competency Lists

Each class is assigned:
- `grade_level`: 9, 10, 11, etc.
- `competency_list_id`: e.g., "klasse-9-chemie" or "klasse-10-chemie"
- `list_source`: "system" (from `kompetenzlisten/` directory) or "teacher" (uploaded)

### Student Dashboard Filter

`_get_student_competencies(student_id)` returns only competencies from the student's class list. This ensures:
- Klasse 9 students see only Klasse 9 competencies (IDs `e.901`-`n.1021`)
- Klasse 10 students see only Klasse 10 competencies (IDs `e.1001`-`n.1103`)
- Records are filtered to match the class competency IDs

### Teacher Coverage Page

The coverage page (`/teacher/coverage`) now has a class selector dropdown. The "Unterrichtsstand" (active_ids) is stored per class, not globally.

### Creating New Lists

Use the conversion script:
```bash
python convert_csv_to_json.py \
    --input-kompetenzen meine-klasse-10.csv \
    --input-fragen meine-fragen.csv \
    --name "Chemie Klasse 10" \
    --grade 10
```

See `KOMPETENZLISTEN_WORKFLOW.md` for detailed workflow.

## Implementation Phases

| Phase | Status | Content |
|-------|--------|---------|
| 0 | done | FastAPI + MSAL login → /auth/me works, roles detected |
| 1 | done | Class groups + student lists (originally Graph API, now SQLite + admin UI) |
| 2 | done | SQLite: read/write competency records + Nachweise (replaces MS Lists) |
| 3 | done | PDF test generator (pdf_engine.py integrated) |
| 4 | done | Grade calculator + student dashboard (score card + Planungsmodus) |
| 5 | done | Bookings (BOOKINGS_PAGE_URL link after test request confirmation) |
| 6 | done | Student test request workflow (pending → teacher review → PDF) |
| 7 | done | CSV upload + admin editor (kompetenzen, questions); thema grouping; test preview |
| 8 | done | Grading scale: CSV presets, upload, editable thresholds; proven-comps in Unterrichtsstand grade |
| 9 | done | Kompetenzanträge: student claim workflow, teacher review, inline dashboard forms |
| 10 | done | DEV_MODE pre-populated SQLite; Git repo + Uberspace deployment |
| 11 | done | SQLite persistence for all data (test_requests, kompetenzantraege, classes, members) |
| 12 | done | Class management admin UI (/admin/classes): add/delete classes, manage + CSV-import members |
| 13 | done | Student migration: transfer competency records when email changes |


---

## ⚠️ DEV-MODE Status (Current Branch: agent-dev)

**This documentation reflects the `agent-dev` branch state which includes DEV_MODE-only features.**

### DEV_MODE Features (NOT in production/main)

| Feature | DEV_MODE | Production |
|---------|----------|------------|
| Login | Fake login form (`/dev-login`) | Azure AD OAuth |
| Test Users | Anna, Max, Lehrer | Real school users |
| Test Classes | 9a (Dev), 10a (Dev) | Real classes from Azure AD |
| Competency Lists | Multiple (Klasse 9, 10, teacher uploads) | Single global list |
| Data Storage | SQLite + JSON files | SQLite (production) |
| CSV Upload | Full workflow for teachers | Admin only |

### Switching to Production

To use this code in production (`main` branch):

1. Set `DEV_MODE=false` in `.env`
2. Configure Azure AD credentials
3. Remove or disable test users and classes
4. Consider: Production uses single global competency list, not class-specific

### DEV_MODE Test Credentials

| User | Email | Password | Class |
|------|-------|----------|-------|
| Anna Beispiel | anna@schule.de | (any) | 9a |
| Max Mustermann | max@schule.de | (any) | 10a |
| Lehrer (Dev) | lehrer@schule.de | (any) | — |



---

## Migration Guide: Old → New ID Format

If migrating from the old integer ID format (2026-03 or earlier), run these steps:

### 1. Backup Database
```bash
cp dashboard.db dashboard.db.backup.pre-migration
```

### 2. Update JSON Files
All files in `kompetenzlisten/` must use new ID format:
```python
# Old: {"id": 901, "typ": "einfach"}
# New: {"id": "e.901", "typ": "einfach"}

# Migration script (run once):
python3 << 'EOF'
import json, os
for f in os.listdir('kompetenzlisten'):
    if f.endswith('.json') and not f.endswith('-questions.json'):
        with open(f'kompetenzlisten/{f}') as file:
            data = json.load(file)
        for c in data.get('competencies', []):
            old_id = c['id']
            if isinstance(old_id, int):
                prefix = 'n' if c['typ'] == 'niveau' else 'e'
                c['id'] = f"{prefix}.{old_id}"
        with open(f'kompetenzlisten/{f}', 'w') as file:
            json.dump(data, file, indent=2)
        print(f"Migrated {f}")
EOF
```

### 3. Restart Server
Database migration runs automatically on startup via `_migrate_competency_ids_to_text()` in `db.py`.

### 4. Verify
```bash
sqlite3 dashboard.db "SELECT competency_id FROM active_ids LIMIT 5"
# Should show: e.901, e.902, n.989, ... (not 901, 902, 989)
```

---

## Quick Reference: ID Formats

| Context | Old (pre-2026-03) | New (current) |
|---------|-------------------|---------------|
| JSON files | `"id": 901` | `"id": "e.901"` |
| Database | `INTEGER` | `TEXT` |
| Python | `int` | `str` |
| Templates | `{{ k.id }}` → `901` | `{{ k.id }}` → `e.901` |
| JavaScript | `parseInt(cb.value)` | `cb.value` (direct) |
| CSV headers | `901;902;...` | `e.901;e.902;...` |

---

**Last updated:** 2026-03-21
**Version:** 2.0 (String IDs with type prefix)


---

## Recent Changes (2026-03-23) - agent-dev Branch

### Database Schema Updates
Required migrations for production deployment:

```sql
-- Add grade_level to classes
ALTER TABLE classes ADD COLUMN grade_level INTEGER;

-- Add legacy columns for backward compatibility
ALTER TABLE classes ADD COLUMN competency_list_id TEXT;
ALTER TABLE classes ADD COLUMN list_source TEXT DEFAULT 'system';

-- Update active_ids for class-specific support
ALTER TABLE active_ids RENAME TO active_ids_old;
CREATE TABLE active_ids (
    competency_id TEXT NOT NULL,
    class_id TEXT,
    PRIMARY KEY (competency_id, class_id)
);
INSERT INTO active_ids (competency_id, class_id) 
SELECT competency_id, NULL FROM active_ids_old;
DROP TABLE active_ids_old;
CREATE INDEX idx_active_ids_class ON active_ids(class_id);
```

### Features Added/Fixed

| Feature | Status | Notes |
|---------|--------|-------|
| Class creation with grade_level | ✅ | Now required field in admin UI |
| Teacher competency lists | ✅ | Upload CSV, assign to classes |
| Question upload formats | ✅ | CSV (row/column) + JSON supported |
| Test generator | ✅ | Loads questions from class-specific lists |
| Test requests (pending) | ✅ | Shows competencies from student's class |
| Logout | ✅ | Full Azure AD session termination |
| Logo | ✅ | Must be copied to static/logo.png |

### CSV Formats for Questions

**Row-based** (standard):
```csv
competency_id;frage
e.901;Frage 1
e.901;Frage 2
e.902;Frage 3
```

**Column-based** (exported from spreadsheets):
```csv
1;2;3;4;5
e.901 Q1;e.902 Q1;e.903 Q1;e.904 Q1;e.905 Q1
e.901 Q2;e.902 Q2;e.903 Q2;e.904 Q2;e.905 Q2
```

### Known Limitations

- **Multi-subject support**: Tables exist but UI not fully implemented
- **Student test requests**: No class_id stored, uses student's class lookup
- **Question display in pending tests**: Only shows request's competencies (not all class competencies)

### Deployment Checklist

1. Backup database: `cp dashboard.db dashboard.db.backup.$(date +%Y%m%d)`
2. Run schema migrations (see above)
3. Copy logo: `scp static/logo.png user@server:~/app/static/`
4. Deploy code: `git pull && systemctl --user restart kompetenz`
5. Verify: Check `/tests/builder` loads questions correctly

---

## Recent Changes (2026-03-28) - agent-dev Branch

### OneNote → Backup-JSON Konvertierung (`onenote_to_backup.py`)

Neues eigenständiges Skript zum Einlesen des Klassennotizbuchs aus OneNote/SharePoint und Erzeugen einer Backup-JSON-Datei, die über `/admin/classes/{class_id}/members/import` hochgeladen werden kann.

**Abhängigkeiten:** `pip install beautifulsoup4` (zusätzlich zu requirements.txt)

**Konfiguration (oben im Skript anpassen):**
```python
TENANT_ID = "..."                    # Azure AD Tenant
CLIENT_ID = "..."                    # Azure AD App (Public Client Flow muss aktiv sein)
SITE_URL = "https://..."             # SharePoint-Site-URL
NOTEBOOK_NAME = "..."                # Exakter Name des Notizbuchs
EINFACH_LIST_ID = "klasse-9-chemie"  # System-Liste oder Teacher-Listen-ID
NIVEAU_LIST_ID  = "teacher-..."      # Teacher-Listen-ID aus DB (z.B. "9 SJ 25,26")
CLASS_ID = "..."                     # Klassen-ID im Dashboard (UUID)
STUDENT_UPN_MAP = {"Name": "upn@..."}  # OneNote-Abschnittsnamen → E-Mail
```

**Authentifizierung:** MSAL Device Flow (`Notes.Read.All` Scope) — kein Admin-Consent nötig.

**Was wird eingelesen:**
- **Unterrichtskompetenzen** (`einfach`): Checkbox-Tabelle — ⚠ Graph API exportiert keine Checkbox-Zustände aus Tabellen, daher 0 Ergebnisse. Freitext-Checkboxen (außerhalb von Tabellen) würden funktionieren.
- **Projektkompetenzen** (`niveau`): Tabelle mit Experte/Advanced/Beginner-Spalten — Link in Zelle = erreicht; höchstes Level wird gespeichert.

**ID-Mapping:** Lädt IDs zuerst vom Live-Server (`/api/competencies/{list_id}`), Fallback auf lokale JSON-Datei. Getrennte Listen für einfach/niveau möglich (relevant wenn Teacher-Liste aktiv ist).

**Kompetenz-Matching:** Exakter → Substring → Word-Overlap (≥60%). Nicht gematchte Namen werden vollständig ausgegeben.

**Robustheit:** Retry-Logik bei 429/5xx (bis zu 4 Versuche, Retry-After Header wird respektiert). Fehler bei einzelnen Schülern überspringen den Schüler statt das Skript zu crashen.

### Neuer API-Endpoint

`GET /api/competencies/{list_id}` — öffentlich (kein Login nötig), gibt `[{id, name, typ}]` zurück. Sucht zuerst in System-Listen (`kompetenzlisten/*.json`), dann in Teacher-Listen (SQLite `teacher_lists`-Tabelle).

---

## Student Migration (Email Change)

When a student changes their email address, use the **"Schüler umziehen"** feature:

### Workflow
1. Go to **Admin → Klassen verwalten → [Class] → Mitglieder**
2. Click **"✉️ Schüler umziehen / E-Mail ändern"**
3. Select student from dropdown (name/current email auto-populated)
4. Enter new email (and adjust name if needed)
5. Click **"Schüler umziehen"**

### What Gets Transferred
- All `einfach_records` (achieved competencies)
- All `nachweise` (niveau evidence/proofs)
- All `test_requests` (pending test requests)
- Class membership

### Data Model
The migration uses `db.migrate_student()` which:
1. Reads all existing records for old student_id
2. Deletes old `class_members` entry
3. Creates new `class_members` entry with new student_id (email)
4. Re-inserts all competency records with new student_id
5. Updates `test_requests` to point to new student_id
6. Deletes old competency records

---

**Last updated:** 2026-03-28
**Branch:** agent-dev
**Commit:** onenote_to_backup + /api/competencies endpoint + student migration
