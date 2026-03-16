# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TestGenerator is a Flask web app that generates customized assessment tests as PDFs from CSV data. Users upload competency definition CSVs and a questions CSV, select competencies, preview/adjust question assignments, and download a branded PDF.

## Running the App

```bash
python app5.py
```

Runs at `http://localhost:5000/` in debug mode. No build step required.

**Dependencies** (install via pip if missing):
- `flask`
- `pandas`
- `reportlab`

## Active Version

**`app5.py` is the current active version.** Earlier files (`app.py`–`app4.py`) are legacy and kept for reference. `app4.py` (image upload during preview) is non-functional.

Templates live in `Templates/` (capital T). Flask resolves this on macOS (case-insensitive FS) but it would break on Linux.

Template mapping:
- `app5.py` → `Templates/upload.html`, `Templates/select3.html`, `Templates/test_preview5.html`
- `app3.py` → `Templates/select3.html`, `Templates/test_preview3.html`

`static/` contains `logo.png` (used in PDFs), `logo2.png` (alternative), and `style.css` (not currently linked in templates).

## CSV Format Requirements

**Competency CSV** (semicolon-delimited) must have columns:
- `ID` — numeric competency identifier
- `Kompetenz` — competency description text

**Questions CSV** (semicolon-delimited):
- Column headers are competency IDs (matching those in the competency CSV)
- Each column contains the pool of questions for that competency

## Application Flow

1. `GET /` → `upload.html`: upload one questions CSV + one or more competency CSVs
2. `POST /upload` → saves files to `uploads/`, redirects to `/select/<filenames>`
3. `GET /select/<kompetenzen_filenames>/<fragen_filename>` → `select3.html`: renders competency checkboxes with name/date/zusatzinfo fields
4. `POST /generate` → `test_preview5.html`: randomly pre-selects one question per competency, shows dropdowns for manual adjustment
5. `POST /download_final` → calls `create_pdf()`, serves PDF from `outputs/`

## PDF Generation

`create_pdf()` in `app5.py` uses ReportLab's canvas API directly (not Platypus/RLPDF). Key rendering functions:
- `draw_header()` — logo (`static/logo.png`), name/date/zusatzinfo in top-right
- `draw_text_wrapped()` — line-wraps text with inline chemical formula support. **Known issue:** this function has no `return` statement, so it implicitly returns `None`; `create_pdf()` guards against this with a `None`-check and resets `y_pos`.
- `format_chemical_formula()` / `draw_chemical_formula()` — parses patterns like `H2O` and renders numbers as subscripts (smaller font, y-offset −3). `format_chemical_formula()` uses `str.find()` internally, so formulas with a repeated element token (e.g. `C6H12O6`) may mis-locate the second occurrence.

Layout: 2 questions per page, each occupying half the page height below the header.

`/download_pdf` is a legacy route still present in `app5.py` but superseded by `/download_final`. The latter passes questions as `{"kid": ..., "text": ...}` dicts so the PDF labels each question with its competency ID.

## Testing Chemical Formula Rendering

```bash
python test_chemical_formula.py
```

Generates a test PDF with various chemical formulas to verify subscript rendering.
