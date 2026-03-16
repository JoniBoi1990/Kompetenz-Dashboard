# AGENT RULES — Kompetenz Dashboard

These rules apply to all AI agents working in this repository.

The goal is to extend the system carefully without breaking existing functionality.

---

# 1. PROJECT PURPOSE

This repository contains a web application called:

Kompetenz-Dashboard

The system is used by a school to:

- track student competencies
- calculate grades
- request competency tests
- generate PDF tests
- manage competency lists

The system must remain simple and maintainable.

---

# 2. CORE ARCHITECTURE

Backend
- Python
- FastAPI

Frontend
- Jinja2 templates
- vanilla JavaScript

Data Layer
- Microsoft Graph API
- Microsoft Lists

Deployment
- Uberspace hosting
- uvicorn main:app

The architecture is intentionally simple.

---

# 3. STRICT CONSTRAINTS

Agents MUST NOT introduce:

- Docker
- PostgreSQL
- Redis
- Celery
- React
- Node.js
- npm build systems
- complex frontend frameworks

The system must remain deployable with:

uvicorn main:app

---

# 4. DEVELOPMENT PRINCIPLES

Follow these principles:

1. Prefer small incremental changes
2. Avoid rewriting large parts of the system
3. Keep logic primarily in Python
4. Keep templates simple
5. Avoid unnecessary dependencies

---

# 5. PRESERVE EXISTING FEATURES

The following systems must continue working:

- student dashboard
- competency tracking
- grade calculator
- test generator
- student test request workflow
- CSV upload for competencies and questions
- admin competency editor
- grading scale editor

Breaking these features is not allowed.

---

# 6. SENSITIVE FILES

These files are critical.

Do not modify them unless absolutely necessary:

auth.py
graph.py
pdf_engine.py

If modification is required, explain the reason first.

---

# 7. UI CONSISTENCY

Follow existing patterns in the templates directory.

Do NOT:

- introduce new UI frameworks
- introduce complex client-side logic
- add large JavaScript systems

Keep UI changes minimal and consistent.

---

# 8. CODE MODIFICATION WORKFLOW

Before implementing changes:

Step 1  
Analyze the relevant code.

Step 2  
Explain the minimal modification needed.

Step 3  
Implement the change.

Avoid large refactorings unless explicitly requested.

---

# 9. GIT WORKFLOW

All code changes must be committed.

Commit message format:

agent: <short description>

Example:

agent: show niveau proof options in dashboard

Commits should be small and focused.

Avoid modifying many unrelated files in a single commit.

---

# 10. FILE MODIFICATION GUIDELINES

Prefer modifying:

templates/
main.py

Avoid touching many files.

If possible:
- add helper functions
- avoid rewriting existing logic

---

# 11. DATA MODEL

Competencies are stored in:

kompetenzen.json

Test questions are stored in:

questions.json

Do not change the data format unless explicitly instructed.

---

# 12. WHEN UNSURE

If the correct implementation is unclear:

1. Explain the uncertainty
2. Propose multiple options
3. Ask for clarification
