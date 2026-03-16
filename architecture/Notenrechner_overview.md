# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
pip install -r requirements.txt   # install dependencies (just flask)
python app-web.py                 # full version with config management (recommended)
python app.py                     # simplified version
```

The app runs at http://localhost:5000 in Flask debug mode.

## Architecture

This is a **Python Flask web app** for calculating German school grades (1–6) from chemistry competency assessments.

**Two Flask implementations:**
- `app.py` — minimal version: loads all competencies, calculates grade from POST form
- `app-web.py` — full version: adds `/update_verfuegbare_kompetenzen` and `/get_verfuegbare_kompetenzen` endpoints to manage which competencies are currently active via `data/config.json`

**Data layer (JSON files, no database):**
- `data/kompetenzen.json` — 114 chemistry competencies, each with `id`, `beschreibung`, and `typ` (`"einfach"` or `"niveau"`)
- `data/config.json` — list of currently enabled competency IDs

**Grade calculation:**
- `"einfach"` competencies: 1 point if checked
- `"niveau"` competencies: 0–3 points via dropdown (Anfänger/Fortgeschritten/Experte)
- Total max = 79 + (35 × 3) = 184 points → percentage → grade 1–6 (≥90%, ≥80%, ≥70%, ≥60%, ≥50%, <50%)

**Frontend:** `templates/index.html` — Jinja2 template generating the form dynamically; vanilla JS submits and displays results.

**Data conversion:** `Umwandlung/umwandlung.py` converts `kompetenzen.csv` → `kompetenzen.json` (one-off utility).
