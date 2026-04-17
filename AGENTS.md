# AGENTS.md — Kompetenz-Dashboard

> This file is intended for AI coding agents. It contains project-specific context, conventions, and guidelines.
> Language: German (de) — the project UI and documentation are in German.

---

## Project Overview

**Kompetenz-Dashboard** is a Microsoft 365-connected student dashboard for chemistry competency tracking, PDF test generation, and appointment booking. It is used in a German school environment (Birklehof) to track student competencies in chemistry classes.

### Key Capabilities

- **Competency Tracking:** Two types of competencies — "einfach" (basic, achieved/not achieved) and "niveau" (leveled: Beginner/Advanced/Expert)
- **Student Dashboard:** Students view their progress, plan scenarios, and submit competency claims
- **Teacher Interface:** Class overview, individual student competency grids, test generation, and administrative functions
- **PDF Test Generator:** Creates personalized competency tests with randomized questions
- **Grade Calculation:** Automatic grade calculation based on achieved competencies
- **Backup/Restore:** JSON-based backup system for competency records
- **OneNote Sync:** Automatic synchronization of competencies from OneNote class notebooks (daily at 02:00 or manual trigger)
- **XP Progress Bar:** RPG-style visual progress indicator with gradient colors (green→blue→purple)
- **Unauthorized Access Page:** Info page for non-chemistry students with average progress display

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.10+) |
| Templates | Jinja2 (server-side rendered HTML) |
| Database | SQLite (`dashboard.db` — file-based, auto-created) |
| Authentication | MSAL Python (Microsoft Azure AD) + itsdangerous signed cookies |
| HTTP Client | httpx (synchronous) |
| PDF Engine | ReportLab |
| Configuration | pydantic-settings (.env file) |
| CSS | Vanilla CSS (no frameworks, no npm) |

**Explicitly NOT used:**
- No Docker
- No React/Vue/Angular (no npm at all)
- No PostgreSQL/MySQL (SQLite only)
- No SharePoint Lists anymore (replaced by SQLite)

---

## Project Structure

```
Kompetenz-Dashboard/
├── main.py                   # FastAPI app + all routes (~2700 lines)
├── config.py                 # Pydantic settings (.env loading)
├── auth.py                   # MSAL + itsdangerous session cookies
├── db.py                     # SQLite persistence layer (~1000 lines)
├── graph.py                  # MS Graph API client (identity only in prod)
├── pdf_engine.py             # PDF generation with ReportLab
├── backup.py                 # Backup/restore system
├── dashboard.db              # SQLite database (NOT in git)
│
├── convert_csv_to_json.py    # CLI: Convert CSV → JSON competency lists
├── onenote_to_backup.py      # Standalone: OneNote → Backup JSON import
├── onenote_sync.py           # Service: OneNote Graph API integration for auto-sync
│
├── grading_scale.json        # Active grading scale (auto-created)
├── static/logo.png           # School logo (place manually, NOT in git)
├── static/style.css          # Vanilla CSS stylesheet
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base layout with navigation
│   ├── dashboard.html        # Student dashboard (with XP progress bar)
│   ├── teacher.html          # Teacher class overview
│   ├── student_detail.html   # Individual student view (with XP progress bar)
│   ├── unauthorized.html     # Info page for non-chemistry students
│   ├── onenote_config.html   # OneNote sync configuration
│   ├── onenote_history.html  # OneNote sync history
│   └── ... (27 templates total)
│
├── kompetenzlisten/          # Class-specific competency lists (JSON)
│   ├── klasse-9-chemie.json
│   ├── klasse-10-chemie.json
│   └── CLAUDE.md             # ID format spec for new classes
│
├── _samples/                 # Sample CSV files (grading scale presets)
├── _backup/                  # Database backups (auto-created, NOT in git)
├── grading_scales/           # Uploaded custom grading scales
├── _archiv/                  # Archive folder
│
├── requirements.txt          # Python dependencies
├── Procfile                  # Heroku/Uberspace deployment
└── .env / .env.example       # Environment configuration
```

---

## Development Setup

### Local Development

```bash
# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env: Set DEV_MODE=true

# Run development server
uvicorn main:app --reload
# → http://localhost:8000/login
```

### Environment Variables (`.env`)

```bash
# Required
DOMAIN=localhost:8000                    # Production: bhof.uber.space
AZURE_CLIENT_ID=your-client-id           # Azure AD App Registration
AZURE_CLIENT_SECRET=your-client-secret   # Azure AD Client Secret
AZURE_TENANT_ID=your-tenant-id           # Azure AD Tenant ID
SESSION_SECRET=change-me                 # Generate: python -c "import secrets; print(secrets.token_hex(32))"

# Optional
DEV_MODE=false                           # Set to true for local dev (enables /dev-login)
USE_BOOKINGS_API=false                   # Microsoft Bookings integration
BOOKINGS_PAGE_URL=https://outlook.office.com/book/...
SHAREPOINT_SITE_ID=                      # Legacy, mostly unused
```

### DEV_MODE

When `DEV_MODE=true`:
- `/dev-login` endpoint becomes available (bypasses Azure AD)
- Test users: `anna@schule.de` (Klasse 9), `max@schule.de` (Klasse 10), `lehrer@schule.de`
- Sample data is auto-populated on first run

**⚠️ Never commit DEV_MODE changes to git.**

---

## Architecture

### Authentication Flow

1. User visits `/login`
2. Redirect to Microsoft Azure AD (unless DEV_MODE)
3. Callback to `/auth/callback`
4. Session stored in signed cookie (itsdangerous, 8h TTL, httponly + samesite=lax)
5. Cookie contains: `{oid, upn, display_name, roles, access_token, id_token}`

**Role Detection:**
- Teacher if: `roles` claim contains `"Lehrer"` OR UPN contains `@lehrer.` OR (Birklehof-specific) UPN ends with `@birklehof.de`
- Student if: UPN ends with `@s.birklehof.de`

**Student Identity:** Uses UPN (email) as `student_id`, NOT Azure AD Object ID.

### Data Model

**Core Tables (SQLite):**

| Table | Purpose |
|-------|---------|
| `einfach_records` | Basic competency achievements (student_id, competency_id, achieved) |
| `nachweise` | Niveau competency proofs with evidence URLs |
| `active_ids` | Unterrichtsstand (currently teaching) per class |
| `test_requests` | Pending student test requests |
| `kompetenzantraege` | Student competency claims pending review |
| `classes` | Class definitions with competency list assignments |
| `class_members` | Student-to-class memberships |
| `teacher_lists` | Custom competency lists uploaded by teachers |

**Competency ID Format:**
- **Always strings with type prefix:** `e.901` (einfach), `n.989` (niveau)
- **Never integers** — this was a major migration
- Ranges: Klasse 9 Einfach `e.901`–`e.988`, Niveau `n.989`–`n.1021`
- Ranges: Klasse 10 Einfach `e.1001`–`e.1070`, Niveau `n.1071`–`n.1103`

See `kompetenzlisten/CLAUDE.md` for complete ID specification.

### Grade Calculation

```python
max_punkte = Σ(3 if niveau else 1) for active competencies
gesamtpunkte = Σ(1 for einfach achieved) + Σ(niveau_level for niveau)
prozent = gesamtpunkte / max_punkte × 100
note = first match from grading_scale where prozent >= min_percent
```

**Unterrichtsstand basis** = `active_ids ∪ proven_ids` (self-taught competencies count).

### Bulk Competency Assignment

Teachers can assign "einfach" competencies to multiple students simultaneously from the **Unterrichtsstand** page:

1. Click on a competency row (not the checkbox) to open the bulk assignment modal
2. Select students via checkboxes (with "All/None/Invert" filter buttons)
3. Save assigns the competency to all selected students

**Implementation:**
- Route: `POST /teacher/coverage/bulk-assign`
- Template: `templates/coverage.html` (modal with inline JavaScript/CSS)
- Only "einfach" competencies support bulk assignment (niveau requires evidence URL)

### XP Progress Bar

RPG-style progress indicator displayed in:
- Student dashboard (main view + planning mode)
- Teacher student detail view
- Unauthorized page (showing average of all students)

**Color Scheme (based on percentage):**
- 🔴 **Red** (`xp-red`): < 20% — needs attention
- 🟡 **Yellow** (`xp-yellow`): 20% - 45% — getting started
- 🟢 **Green** (`xp-green`): 45% - 80% — good progress
- 🔵 **Blue** (`xp-blue`): ≥ 80% — excellent

**Features:**
- Color changes dynamically based on percentage
- Animated width transition
- "X% XP" text overlay
- Updates in real-time in planning mode when basis toggles (Unterrichtsstand vs. Schuljahr)

**CSS classes:** `.xp-bar-container`, `.xp-bar-fill`, `.xp-bar-text`, plus color classes `.xp-red`, `.xp-yellow`, `.xp-green`, `.xp-blue`

### Unauthorized Access Handling

Users with `@birklehof.de` (non-teachers) or `@s.birklehof.de` (not in any class) see `unauthorized.html`:
- Birklehof logo
- XP progress bar showing average progress of all enrolled students
- Info text explaining this is for chemistry students only
- Logout button

Implemented in `main.py:student_dashboard()` with helper `calculate_average_progress()`.

---

## OneNote Sync Integration

Automatic synchronization of competencies from OneNote class notebooks to the dashboard.

### Configuration

Each class can be configured independently via `Lehrer → Klasse → OneNote Konfiguration`:

- **SharePoint Site URL:** The site hosting the class notebook
- **Notebook Name:** Exact name of the OneNote notebook
- **Student Mapping:** Optional JSON mapping of OneNote names to UPNs
- **Enabled:** Toggle to activate/deactivate sync

### How It Works

1. **Data Source:** Reads from "Kompetenznachweise" section in each student's notebook
2. **Einfach Competencies:** Parsed from "Unterrichtskompetenzen" page (checkboxes)
3. **Niveau Competencies:** Parsed from "Projektkompetenzen" page (level columns)
4. **Merge Behavior:** 
   - Einfach: Added only if not already achieved
   - Niveau: Added only if no identical entry exists (same URL + same level). Multiple evidence entries per competency are allowed (different URLs or different levels).
5. **Scheduling:** Automatic daily sync at 02:00 UTC, or manual trigger anytime

### Database Tables

- `onenote_sync_config`: Per-class configuration
- `onenote_sync_history`: Sync run history with details of added competencies

### Files

- `onenote_sync.py`: Service module with Graph API integration
- `templates/onenote_config.html`: Configuration UI
- `templates/onenote_history.html`: History view with detail modal

### Authentication Note

Manual sync uses the triggering teacher's access token. Automatic scheduled sync requires either:
- Azure AD Service Principal with Application permissions, OR
- Stored refresh token (with periodic re-authorization)

---

## Key Conventions

### Code Style

- **Language:** Python 3.10+ with type hints
- **Quote style:** Double quotes for strings
- **Function naming:** `snake_case`
- **Line length:** ~100 characters (pragmatic, not strict)
- **Comments:** German in user-facing code, English for technical notes

### Template Patterns

**Thema Grouping (essential pattern):**
```jinja2
{% set ns = namespace(last_thema=None) %}
{% for k in einfach_kompetenzen %}
  {% if k.thema != ns.last_thema %}{% set ns.last_thema = k.thema %}
    <tr class="thema-header">...</tr>
  {% endif %}
{% endfor %}
```

**Never use `parseInt()` or `int()` on competency IDs** — they are strings.

### CSV Formats

**Competency lists:**
- Semicolon-separated UTF-8 with BOM (`utf-8-sig`)
- Headers: `id;name;typ;thema;anmerkungen`

**Grading scales:**
- Comma-separated UTF-8
- Headers: `Note,Dezimal,Prozent (Schwelle ab),Prozentbereich (ca.)`

**Test questions:**
- Row 0 = competency ID headers (`e.901;e.902;...`)
- Rows 1–N = question variants

---

## Git Workflow

| Branch | Purpose |
|--------|---------|
| `main` | Stable production — deployed on Uberspace |
| `agent-dev` | Development branch for AI agents |

**⚠️ CRITICAL:**
- **Agents commit only to `agent-dev`**
- **Never merge `agent-dev` → `main` directly** — user reviews and merges
- Commit format: `agent: <short description>`
- `agent-dev` contains DEV_MODE-only code that must not reach production

---

## Deployment

### Uberspace Deployment

```bash
# Deploy update (after user merges agent-dev → main)
ssh bhof@larissa.uberspace.de "cd ~/Kompetenz-Dashboard && git pull && systemctl --user restart kompetenz"

# View logs
ssh bhof@larissa.uberspace.de "journalctl --user -u kompetenz -f"
```

### Service Configuration

Systemd user service (`~/.config/systemd/user/kompetenz.service`):
```ini
[Unit]
Description=Kompetenz Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/bhof/Kompetenz-Dashboard
Environment=PATH=/home/bhof/.local/bin:/usr/bin
ExecStart=/home/bhof/.local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=default.target
```

---

## Security Considerations

### Authentication
- MSAL scopes: `User.Read` (identity), `Notes.Read.All` (OneNote sync)
- Session cookies: 8h TTL, httponly, samesite=lax
- Role detection based on Azure AD claims + UPN patterns

### Data Protection
- SQLite database NOT in git (`.gitignore`)
- Backup files NOT in git
- `.env` with secrets NOT in git
- School logo (`static/logo.png`) NOT in git

### Input Validation
- Competency IDs validated as strings with `e.` or `n.` prefix
- File uploads restricted to CSV/JSON
- Backup file paths validated to stay within `_backup/` directory

---

## Testing

**No automated test suite exists.** Testing is manual:

1. Start with `DEV_MODE=true`
2. Use test accounts: `anna@schule.de`, `max@schule.de`, `lehrer@schule.de`
3. Verify key workflows:
   - Student dashboard view
   - Teacher class overview
   - Competency recording
   - PDF generation
   - Test request flow

---

## Common Tasks

### Adding a New Class

1. **Create competency list:**
   ```bash
   python convert_csv_to_json.py \
     --input-kompetenzen _samples/klasse-11-chemie.csv \
     --input-fragen _samples/klasse-11-chemie-fragen.csv \
     --output-dir kompetenzlisten/ \
     --name "Chemie Klasse 11" \
     --grade 11
   ```

2. **Add class in web UI:** `Admin → Klassen verwalten → Neue Klasse`

3. **Assign competency list:** Click class → "Kompetenzliste zuweisen"

4. **Add students:** `Admin → Klassen verwalten → [Klasse] → Mitglieder`

### Updating the Grading Scale

Upload CSV via `Admin → Notenschlüssel` or place in `grading_scales/`.

### Creating a Backup

```python
import backup
backup.create_manual_backup("class-id", "teacher@schule.de")
```

Backups are stored in `_backup/manual/{class_id}/`.

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| Unterrichtsstand shows 0 competencies | No competency_list_id assigned | Admin → Klasse → Kompetenzliste zuweisen |
| Student not found | Wrong UPN format | Use exact email from Azure AD |
| Integer ID errors | Old code using `int()` on IDs | IDs are strings: `e.901`, not `901` |
| PDF logo missing | `static/logo.png` not present | Add school logo manually |
| Dev login fails | DB already initialized | Delete `dashboard.db` and restart |

---

## File Size Reference

- `main.py`: ~2700 lines (FastAPI routes)
- `db.py`: ~1000 lines (SQLite layer)
- `auth.py`: ~175 lines (MSAL + sessions)
- `pdf_engine.py`: ~170 lines (ReportLab PDF)
- `backup.py`: ~500 lines (Backup/restore)
- `graph.py`: ~350 lines (MS Graph API)

---

## Contact & Context

- **School:** Birklehof (German boarding school)
- **Subject:** Chemistry (Chemie)
- **Grades:** 9–10 (expandable)
- **Production URL:** https://bhof.uber.space
- **Hosting:** Uberspace (larissa.uberspace.de)

---

## AI Skills

### Code Reviewer

Ein lokaler Skill zur Code-Analyse befindet sich in `.agents/skills/code-reviewer/`.

**Verwendung:**
```bash
# Duplikate finden
python3 .agents/skills/code-reviewer/scripts/find_duplicates.py .

# Unbenutzten Code finden
python3 .agents/skills/code-reviewer/scripts/find_unused.py .
```

Der Skill analysiert Python-Code und erstellt konkrete Verbesserungsvorschläge für:
- Duplizierte Funktionen
- Unbenutzte Imports, Funktionen, Klassen
- Code-Smells

**Keine automatischen Änderungen** — nur Vorschläge!

---

*Last updated: 2026-04-17 by AI agent analysis*
