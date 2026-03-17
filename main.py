"""
Kompetenz-Dashboard — FastAPI + Jinja2 + Microsoft 365
No database, no Docker, no React.  M365 is the data layer.
"""
import csv
import io
import json
import random
import secrets
import uuid
from pathlib import Path
from datetime import date, datetime, timezone
from urllib.parse import quote

from fastapi import FastAPI, Request, Depends, Form, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import db
from config import settings
from pdf_engine import create_pdf

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Kompetenz-Dashboard")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

NIVEAU_LABELS = {
    0: "noch nicht nachgewiesen",
    1: "Beginner",
    2: "Advanced",
    3: "Expert",
}

_KOMPETENZEN: list[dict] = []
_KOMPETENZ_MAP: dict[int, dict] = {}
_EINFACH: list[dict] = []
_NIVEAU: list[dict] = []
_QUESTIONS: dict[str, list[str]] = {}
_GRADING_SCALE: list[dict] = []  # [{note, dezimal, min_percent}, ...] sorted desc by min_percent

# Built-in grade scale preset CSV files
_GRADE_SCALE_PRESETS = [
    {
        "id": "default",
        "label": "50\u2009%\u00a0\u2192 3\u22124 (Standard)",
        "file": BASE_DIR / "_samples" / "Note-Dezimal-ProzentSchwelleab-Prozentbereichca-2.csv",
    },
    {
        "id": "alt",
        "label": "50\u2009%\u00a0\u2192 3\u2212 (Strenger)",
        "file": BASE_DIR / "_samples" / "Note-Dezimal-ProzentSchwelleab-Prozentbereichca.csv",
    },
]

_GRADE_SCALES_DIR = BASE_DIR / "grading_scales"  # uploaded scale files


def _parse_grade_scale_rows(reader: csv.DictReader) -> list[dict]:
    """Parse rows from a DictReader into [{note, dezimal, min_percent}], excludes 6."""
    result = []
    for row in reader:
        dezimal = float(row["Dezimal"])
        if dezimal >= 6.0:
            continue
        result.append({
            "note": row["Note"].strip(),
            "dezimal": dezimal,
            "min_percent": float(row["Prozent (Schwelle ab)"]),
        })
    return result


def _parse_grade_scale_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return _parse_grade_scale_rows(csv.DictReader(f))


def _parse_grade_scale_bytes(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    return _parse_grade_scale_rows(csv.DictReader(io.StringIO(text)))


def _note_at_50(scale: list[dict]) -> str:
    """Return the note string that a student achieves at exactly 50%."""
    note = "6"
    for entry in scale:
        if 50.0 >= entry["min_percent"]:
            note = entry["note"]
            break
    return note


def _safe_note_filename(note: str) -> str:
    """Convert a note string to a safe filename component."""
    return note.replace("\u2212", "-").replace("/", "").replace("\\", "").replace(" ", "")


def _get_all_presets() -> list[dict]:
    """Return built-in + uploaded presets as [{id, label, file}]."""
    result = list(_GRADE_SCALE_PRESETS)
    if _GRADE_SCALES_DIR.exists():
        for f in sorted(_GRADE_SCALES_DIR.glob("*.csv")):
            try:
                _parse_grade_scale_csv(f)  # validate
                stem = f.stem.replace("_", " ")
                result.append({"id": f"upload_{f.stem}", "label": stem, "file": f})
            except Exception:
                pass
    return result


def _default_grading_scale() -> list[dict]:
    return _parse_grade_scale_csv(_GRADE_SCALE_PRESETS[0]["file"])


def _reload_grading_scale() -> None:
    global _GRADING_SCALE
    p = BASE_DIR / "grading_scale.json"
    _GRADING_SCALE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else _default_grading_scale()


def _reload_kompetenzen() -> None:
    global _KOMPETENZEN, _KOMPETENZ_MAP, _EINFACH, _NIVEAU
    _KOMPETENZEN = json.loads((BASE_DIR / "kompetenzen.json").read_text(encoding="utf-8"))
    _KOMPETENZ_MAP = {k["id"]: k for k in _KOMPETENZEN}
    _EINFACH = sorted(
        (k for k in _KOMPETENZEN if k["typ"] == "einfach"),
        key=lambda k: (k.get("thema") or 999, k["id"]),
    )
    _NIVEAU  = sorted(
        (k for k in _KOMPETENZEN if k["typ"] == "niveau"),
        key=lambda k: k["id"],
    )
    themen: dict[int, list] = {}
    for k in _EINFACH:
        themen.setdefault(k.get("thema") or 0, []).append(k)
    templates.env.globals["einfach_kompetenzen"] = _EINFACH
    templates.env.globals["niveau_kompetenzen"]  = _NIVEAU
    templates.env.globals["einfach_nach_thema"]  = themen


def _reload_questions() -> None:
    global _QUESTIONS
    p = BASE_DIR / "questions.json"
    _QUESTIONS = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# Make these available in every template without passing them explicitly
templates.env.globals["NIVEAU_LABELS"] = NIVEAU_LABELS
templates.env.globals["config"] = settings

# Initial load
_reload_kompetenzen()
_reload_questions()
_reload_grading_scale()

# ---------------------------------------------------------------------------
# Dev-Modus: In-Memory-Speicher (ersetzt MS Lists wenn DEV_MODE=true)
# Lehrer trägt für "dev-student-001" Daten ein →
# Schüler loggt sich als "dev-student-001" ein und sieht dieselben Daten.
# ---------------------------------------------------------------------------

# Ephemeral store for in-progress test previews (per-process, intentionally lost on restart)
_TEST_PREVIEWS: dict = {}

DEV_STUDENT_OID  = "dev-student-001"
DEV_STUDENT_NAME = "Anna Beispiel"


def _init_dev_db() -> None:
    """Pre-populate SQLite with sample data when in DEV_MODE and DB is empty."""
    if not settings.DEV_MODE:
        return
    # Only populate once — skip if dev student data already exists
    if db.get_einfach_records(DEV_STUDENT_OID):
        return

    # Dev class
    db.add_class("9a (Dev)", "Beispielklasse", class_id="dev-class")
    db.add_class_member("dev-class", DEV_STUDENT_OID, DEV_STUDENT_NAME, "anna@schule.de")

    # Unterrichtsstand: einfach Themen 1–3 + first 10 niveau competencies
    active_einfach = [k for k in _EINFACH if k.get("thema") in (1, 2, 3)]
    active_niveau  = _NIVEAU[:10]
    db.set_active_ids({k["id"] for k in active_einfach} | {k["id"] for k in active_niveau})

    # Dev student: 80 % of active einfach achieved
    n_achieved = round(len(active_einfach) * 0.8)
    for k in active_einfach:
        db.upsert_einfach(
            DEV_STUDENT_OID, DEV_STUDENT_NAME, k["id"],
            achieved=(k in active_einfach[:n_achieved]),
            updated_by="lehrer@lehrer.schule.de",
        )

    # Dev student niveau: 5×Advanced, 3×Beginner, 2×Expert
    for k, lvl in zip(active_niveau, [2, 2, 2, 2, 2, 1, 1, 1, 3, 3]):
        db.add_nachweis(
            DEV_STUDENT_OID, DEV_STUDENT_NAME, k["id"], lvl,
            "https://example.com/nachweis", "Beispiel-Nachweis",
            "lehrer@lehrer.schule.de",
        )


db.init_db()
_init_dev_db()


# ---------------------------------------------------------------------------
# Grade calculation
# ---------------------------------------------------------------------------

def _load_active_ids(token: str) -> set[int]:
    return db.get_active_ids()


def _save_active_ids(token: str, ids: set[int]) -> None:
    db.set_active_ids(ids)


def _get_test_requests() -> dict:
    return db.get_test_requests()


def _save_test_request(req: dict) -> None:
    db.save_test_request(req)


def _create_preview(student_name: str, title: str, competency_ids: list[int],
                    request_id: str | None = None) -> str:
    questions = []
    for cid in competency_ids:
        k = _KOMPETENZ_MAP.get(cid)
        if not k or k["typ"] != "einfach":
            continue
        opts = _QUESTIONS.get(str(cid)) or [k["name"]]
        questions.append({
            "competency_id": cid,
            "competency_name": k["name"],
            "selected": random.choice(opts),
            "options": opts,
        })
    pid = str(uuid.uuid4())
    _TEST_PREVIEWS[pid] = {
        "id": pid, "student_name": student_name, "title": title,
        "request_id": request_id, "questions": questions,
    }
    return pid


def _build_grade_records(einfach_map: dict, nachweise_by_comp: dict) -> list[dict]:
    """Merge einfach records + best-niveau-per-comp into a unified list for calculate_grade()."""
    records = []
    for k in _KOMPETENZEN:
        cid = k["id"]
        if k["typ"] == "einfach":
            r = einfach_map.get(cid, {})
            records.append({"competency_id": cid, "achieved": bool(r.get("achieved")), "niveau_level": 0})
        else:
            entries = nachweise_by_comp.get(cid, [])
            best = max((e.get("niveau_level", 0) for e in entries), default=0)
            records.append({"competency_id": cid, "achieved": False, "niveau_level": best})
    return records


def calculate_grade(records: list[dict], competencies: list[dict] | None = None) -> dict:
    comps = competencies if competencies is not None else _KOMPETENZEN
    max_punkte = sum(3 if k["typ"] == "niveau" else 1 for k in comps)
    record_map = {r["competency_id"]: r for r in records}
    gesamtpunkte = 0
    for k in comps:
        r = record_map.get(k["id"])
        if r is None:
            continue
        if k["typ"] == "einfach":
            gesamtpunkte += 1 if r.get("achieved") else 0
        else:
            gesamtpunkte += int(r.get("niveau_level") or 0)
    prozent = round(gesamtpunkte / max_punkte * 100, 1) if max_punkte else 0
    note = "6"
    for entry in _GRADING_SCALE:
        if prozent >= entry["min_percent"]:
            note = entry["note"]
            break
    return {"gesamtpunkte": gesamtpunkte, "max_punkte": max_punkte, "prozent": prozent, "note": note}


def _load_student_data(token: str, student_id: str) -> tuple[dict, dict, dict, dict | None]:
    """
    Returns (einfach_record_map, nachweise_by_comp, best_nachweis_by_comp, grade).
    Reads from local SQLite database.
    """
    einfach_map: dict = {}
    nachweise_by_comp: dict = {}
    best_nachweis_by_comp: dict = {}
    grade = None

    try:
        einfach_map = db.get_einfach_records(student_id)
        for n in db.get_nachweise(student_id):
            nachweise_by_comp.setdefault(n["competency_id"], []).append(n)
        for cid, entries in nachweise_by_comp.items():
            best_nachweis_by_comp[cid] = max(entries, key=lambda e: e.get("niveau_level", 0))
        grade = calculate_grade(_build_grade_records(einfach_map, nachweise_by_comp))
    except Exception:
        pass

    return einfach_map, nachweise_by_comp, best_nachweis_by_comp, grade


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login")
async def login(request: Request):
    if settings.DEV_MODE:
        return templates.TemplateResponse("dev_login.html", {"request": request})
    state = secrets.token_hex(16)
    url = auth.get_auth_url(state, auth._build_redirect_uri(request))
    return RedirectResponse(url)


@app.post("/dev-login")
async def dev_login(
    display_name: str = Form(...),
    role: str = Form(...),
):
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="Nur im Dev-Modus verfügbar")
    is_teacher = role == "teacher"
    user_info = {
        "oid": "dev-teacher-001" if is_teacher else DEV_STUDENT_OID,
        "upn": f"dev@{'lehrer.' if is_teacher else ''}schule.de",
        "display_name": display_name,
        "roles": ["Lehrer"] if is_teacher else [],
        "is_teacher": is_teacher,
        "access_token": "",
    }
    response = RedirectResponse(url="/teacher" if is_teacher else "/", status_code=302)
    auth.set_session(response, user_info)
    return response


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(f"<h1>Login fehlgeschlagen</h1><p>{error}</p>", status_code=400)
    try:
        token_response = auth.exchange_code(code, auth._build_redirect_uri(request))
    except ValueError as e:
        return HTMLResponse(f"<h1>Token-Fehler</h1><p>{e}</p>", status_code=400)
    user_info = auth.build_user_info(token_response)
    response = RedirectResponse(url="/teacher" if user_info["is_teacher"] else "/", status_code=302)
    auth.set_session(response, user_info)
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    auth.clear_session(response)
    return response


@app.get("/auth/me")
async def auth_me(user: dict = Depends(auth.require_user)):
    return {"oid": user["oid"], "upn": user["upn"],
            "display_name": user["display_name"], "is_teacher": user["is_teacher"]}


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def student_dashboard(request: Request, user: dict = Depends(auth.require_user)):
    if user["is_teacher"]:
        return RedirectResponse("/teacher")

    einfach_map, nachweise_by_comp, best_nachweis_by_comp, _ = _load_student_data(
        user["access_token"], user["oid"]
    )
    active_ids = _load_active_ids(user["access_token"])

    # Recalculate grade filtered by active_ids + proven competencies (Unterrichtsstand basis)
    if active_ids:
        proven_ids = (
            {cid for cid, r in einfach_map.items() if r.get("achieved")}
            | {cid for cid, entries in nachweise_by_comp.items()
               if any(e.get("niveau_level", 0) > 0 for e in entries)}
        )
        grade_comps = [k for k in _KOMPETENZEN if k["id"] in active_ids or k["id"] in proven_ids]
    else:
        grade_comps = None
    grade = calculate_grade(_build_grade_records(einfach_map, nachweise_by_comp), competencies=grade_comps)

    # JSON payloads for client-side planning mode
    kompetenzen_json = json.dumps([{"id": k["id"], "typ": k["typ"]} for k in _KOMPETENZEN])
    current_state: dict = {}
    for k in _EINFACH:
        r = einfach_map.get(k["id"], {})
        current_state[k["id"]] = {"achieved": bool(r.get("achieved")), "niveau_level": 0}
    for k in _NIVEAU:
        entries = nachweise_by_comp.get(k["id"], [])
        best_niv = max((e.get("niveau_level", 0) for e in entries), default=0)
        current_state[k["id"]] = {"achieved": False, "niveau_level": best_niv}
    current_state_json = json.dumps(current_state)
    active_ids_list = json.dumps(sorted(active_ids))
    proven_ids_list = json.dumps(sorted(proven_ids)) if active_ids else "[]"
    grading_scale_json = json.dumps(
        [{"note": e["note"], "min_percent": e["min_percent"]} for e in _GRADING_SCALE]
    )

    # Build antrag lookup dicts for this student
    pending_antraege_by_comp: dict[int, dict] = {}
    rejected_niveau_antraege_by_comp: dict[int, dict] = {}
    for a in db.get_all_kompetenzantraege().values():
        if a["student_id"] != user["oid"]:
            continue
        cid = a["competency_id"]
        if a["status"] == "pending":
            pending_antraege_by_comp[cid] = a
        elif a["status"] == "rejected" and a["typ"] == "niveau":
            existing = rejected_niveau_antraege_by_comp.get(cid)
            if not existing or a["created_at"] > existing["created_at"]:
                rejected_niveau_antraege_by_comp[cid] = a

    antrag_ok = request.query_params.get("antrag_ok")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "einfach_map": einfach_map,
        "nachweise_by_comp": nachweise_by_comp,
        "best_nachweis_by_comp": best_nachweis_by_comp,
        "grade": grade,
        "active_ids": active_ids,
        "kompetenzen_json": kompetenzen_json,
        "current_state_json": current_state_json,
        "active_ids_list": active_ids_list,
        "proven_ids_list": proven_ids_list,
        "grading_scale_json": grading_scale_json,
        "pending_antraege_by_comp": pending_antraege_by_comp,
        "rejected_niveau_antraege_by_comp": rejected_niveau_antraege_by_comp,
        "antrag_ok": antrag_ok,
    })


# ---------------------------------------------------------------------------
# Teacher routes
# ---------------------------------------------------------------------------

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_overview(request: Request, user: dict = Depends(auth.require_teacher_user)):
    groups = db.get_classes()
    pending_count = sum(1 for r in _get_test_requests().values() if r["status"] == "pending")
    pending_antraege_count = sum(
        1 for a in db.get_all_kompetenzantraege().values() if a["status"] == "pending"
    )
    return templates.TemplateResponse("teacher.html", {
        "request": request, "user": user, "groups": groups,
        "pending_count": pending_count, "pending_antraege_count": pending_antraege_count,
    })


@app.get("/teacher/class/{class_id}", response_class=HTMLResponse)
async def teacher_class(class_id: str, request: Request, user: dict = Depends(auth.require_teacher_user)):
    members = db.get_class_members(class_id)
    return templates.TemplateResponse("class_detail.html", {
        "request": request, "user": user, "class_id": class_id, "members": members,
    })


@app.get("/teacher/student/{student_id}", response_class=HTMLResponse)
async def teacher_student_detail(
    student_id: str,
    request: Request,
    class_id: str = "",
    student_name: str = "",
    user: dict = Depends(auth.require_teacher_user),
):
    einfach_map, nachweise_by_comp, best_nachweis_by_comp, grade = _load_student_data(
        user["access_token"], student_id
    )
    active_ids = _load_active_ids(user["access_token"])
    return templates.TemplateResponse("student_detail.html", {
        "request": request,
        "user": user,
        "student_id": student_id,
        "student_name": student_name,
        "class_id": class_id,
        "einfach_map": einfach_map,
        "nachweise_by_comp": nachweise_by_comp,
        "best_nachweis_by_comp": best_nachweis_by_comp,
        "grade": grade,
        "active_ids": active_ids,
    })


@app.post("/records/update")
async def update_record(
    student_id: str = Form(...),
    student_name: str = Form(...),
    competency_id: int = Form(...),
    achieved: str = Form(default=""),
    class_id: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    is_achieved = achieved.lower() in ("1", "true", "on", "yes")
    db.upsert_einfach(student_id, student_name, competency_id, is_achieved, user["upn"])
    return RedirectResponse(
        url=f"/teacher/student/{student_id}?class_id={class_id}&student_name={student_name}",
        status_code=302,
    )


@app.post("/records/nachweis")
async def add_nachweis(
    student_id: str = Form(...),
    student_name: str = Form(...),
    competency_id: int = Form(...),
    niveau_level: int = Form(...),
    evidence_url: str = Form(default=""),
    evidence_name: str = Form(default=""),
    class_id: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    db.add_nachweis(
        student_id, student_name, competency_id, niveau_level,
        evidence_url.strip(), evidence_name.strip() or evidence_url.strip(), user["upn"],
    )
    return RedirectResponse(
        url=f"/teacher/student/{student_id}?class_id={class_id}&student_name={student_name}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Kompetenzanträge — student-initiated competency claims
# ---------------------------------------------------------------------------

@app.post("/antraege/submit")
async def antraege_submit(
    competency_id: int = Form(...),
    typ: str = Form(...),
    beschreibung: str = Form(default=""),
    evidence_url: str = Form(default=""),
    user: dict = Depends(auth.require_user),
):
    if user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Nur für Schüler")
    if typ not in ("einfach", "niveau"):
        raise HTTPException(status_code=400, detail="Ungültiger Typ")

    # Must not already be proven
    einfach_map, nachweise_by_comp, _, _ = _load_student_data(user["access_token"], user["oid"])
    if typ == "einfach":
        if einfach_map.get(competency_id, {}).get("achieved"):
            raise HTTPException(status_code=400, detail="Bereits nachgewiesen")
        if not beschreibung.strip():
            raise HTTPException(status_code=400, detail="Beschreibung erforderlich")
    else:
        entries = nachweise_by_comp.get(competency_id, [])
        if any(e.get("niveau_level", 0) > 0 for e in entries):
            raise HTTPException(status_code=400, detail="Bereits nachgewiesen")
        if not evidence_url.strip():
            raise HTTPException(status_code=400, detail="Link erforderlich")

    # No existing pending antrag for this competency
    for a in db.get_all_kompetenzantraege().values():
        if a["student_id"] == user["oid"] and a["competency_id"] == competency_id and a["status"] == "pending":
            raise HTTPException(status_code=400, detail="Antrag bereits gestellt")

    antrag_id = str(uuid.uuid4())
    antrag = {
        "id": antrag_id,
        "student_id": user["oid"],
        "student_name": user["display_name"],
        "competency_id": competency_id,
        "typ": typ,
        "beschreibung": beschreibung.strip(),
        "evidence_url": evidence_url.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "begruendung": "",
        "niveau_level": None,
    }
    db.save_kompetenzantrag(antrag)
    return RedirectResponse(url="/?antrag_ok=1", status_code=302)


@app.get("/antraege/pending", response_class=HTMLResponse)
async def antraege_pending(request: Request, user: dict = Depends(auth.require_teacher_user)):
    antraege = [
        {**a, "competency_name": (_KOMPETENZ_MAP.get(a["competency_id"]) or {}).get("name", "?")}
        for a in db.get_all_kompetenzantraege().values()
        if a["status"] == "pending"
    ]
    antraege.sort(key=lambda a: a["created_at"])
    return templates.TemplateResponse("antraege_pending.html", {
        "request": request, "user": user, "antraege": antraege,
    })


@app.post("/antraege/accept/{antrag_id}")
async def antraege_accept(
    antrag_id: str,
    niveau_level: int = Form(default=0),
    begruendung: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    antraege = db.get_all_kompetenzantraege()
    a = antraege.get(antrag_id)
    if not a or a["status"] != "pending":
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")

    student_id = a["student_id"]
    student_name = a["student_name"]
    competency_id = a["competency_id"]

    if a["typ"] == "einfach":
        db.upsert_einfach(student_id, student_name, competency_id, True, user["upn"])
        a["status"] = "accepted"
    else:
        if niveau_level < 1 or niveau_level > 3:
            raise HTTPException(status_code=400, detail="Niveau 1–3 erforderlich")
        db.add_nachweis(
            student_id, student_name, competency_id, niveau_level,
            a["evidence_url"], a["evidence_url"], user["upn"],
        )
        a["status"] = "accepted"
        a["niveau_level"] = niveau_level
        a["begruendung"] = begruendung.strip()

    db.save_kompetenzantrag(a)
    return RedirectResponse(url="/antraege/pending", status_code=302)


@app.post("/antraege/reject/{antrag_id}")
async def antraege_reject(
    antrag_id: str,
    begruendung: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    antraege = db.get_all_kompetenzantraege()
    a = antraege.get(antrag_id)
    if not a or a["status"] != "pending":
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    a["status"] = "rejected"
    a["begruendung"] = begruendung.strip()
    db.save_kompetenzantrag(a)
    return RedirectResponse(url="/antraege/pending", status_code=302)


# ---------------------------------------------------------------------------
# Teacher: Unterrichtsstand (which competencies have been covered)
# ---------------------------------------------------------------------------

@app.get("/teacher/coverage", response_class=HTMLResponse)
async def teacher_coverage(request: Request, user: dict = Depends(auth.require_teacher_user)):
    active_ids = _load_active_ids(user["access_token"])
    return templates.TemplateResponse("coverage.html", {
        "request": request, "user": user, "active_ids": active_ids,
    })


@app.post("/teacher/coverage/update")
async def teacher_coverage_update(request: Request, user: dict = Depends(auth.require_teacher_user)):
    form = await request.form()
    ids = {int(v) for k, v in form.multi_items() if k == "active_id"}
    _save_active_ids(user["access_token"], ids)
    return RedirectResponse(url="/teacher/coverage", status_code=302)


# ---------------------------------------------------------------------------
# PDF Test Generator  (nur einfache Kompetenzen)
# ---------------------------------------------------------------------------

@app.get("/tests/builder", response_class=HTMLResponse)
async def test_builder(request: Request, user: dict = Depends(auth.require_user)):
    active_ids = _load_active_ids(user["access_token"])
    active_ids_list = json.dumps(sorted(active_ids))

    if not user["is_teacher"]:
        einfach_map, _, _, _ = _load_student_data(user["access_token"], user["oid"])
        proven_ids = {cid for cid, r in einfach_map.items() if r.get("achieved")}
        reqs = _get_test_requests()
        next_number = sum(1 for r in reqs.values() if r["student_id"] == user["oid"]) + 1
        return templates.TemplateResponse("test_builder.html", {
            "request": request, "user": user,
            "proven_ids": proven_ids,
            "active_ids": active_ids,
            "next_number": next_number,
        })

    groups = db.get_classes()

    return templates.TemplateResponse("test_builder.html", {
        "request": request, "user": user,
        "active_ids": active_ids,
        "active_ids_list": active_ids_list,
        "groups": groups,
    })


@app.post("/tests/generate")
async def generate_test(request: Request, user: dict = Depends(auth.require_teacher_user)):
    form = await request.form()
    selected_ids = [int(v) for k, v in form.multi_items() if k == "competency_ids"]

    if not selected_ids:
        raise HTTPException(status_code=400, detail="Keine Kompetenzen ausgewählt")

    student_name = form.get("student_name", "")
    if not student_name:
        raise HTTPException(status_code=400, detail="Kein Schülername angegeben")

    title = form.get("title", "Kompetenztest")
    pid = _create_preview(student_name, title, selected_ids)
    return RedirectResponse(f"/tests/preview/{pid}", status_code=303)


@app.post("/tests/request", response_class=HTMLResponse)
async def student_test_request(request: Request, user: dict = Depends(auth.require_user)):
    """Student submits a test request — stored for teacher to review and print."""
    if user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Nur für Schüler")

    form = await request.form()
    selected_ids = [int(v) for k, v in form.multi_items() if k == "competency_ids"]
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Keine Kompetenzen ausgewählt")

    # Backend validation: silently drop competency IDs that are already proven
    einfach_map, _, _, _ = _load_student_data(user["access_token"], user["oid"])
    proven_ids = {cid for cid, r in einfach_map.items() if r.get("achieved")}
    selected_ids = [cid for cid in selected_ids if cid not in proven_ids]
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Alle gewählten Kompetenzen bereits nachgewiesen")

    reqs = _get_test_requests()
    number = sum(1 for r in reqs.values() if r["student_id"] == user["oid"]) + 1
    req = {
        "id": str(uuid.uuid4()),
        "student_id": user["oid"],
        "student_name": user["display_name"],
        "competency_ids": selected_ids,
        "title": f"Kompetenznachweis Nr. {number}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    _save_test_request(req)

    return templates.TemplateResponse("test_request_sent.html", {
        "request": request, "user": user, "req": req,
        "bookings_page_url": settings.BOOKINGS_PAGE_URL,
    })


@app.get("/tests/pending", response_class=HTMLResponse)
async def pending_tests(request: Request, user: dict = Depends(auth.require_teacher_user)):
    """Teacher views and confirms pending student test requests."""
    pending = [r for r in _get_test_requests().values() if r["status"] == "pending"]
    pending.sort(key=lambda r: r["created_at"])
    return templates.TemplateResponse("pending_tests.html", {
        "request": request, "user": user, "pending": pending,
    })


@app.post("/tests/confirm/{req_id}")
async def confirm_test(req_id: str, request: Request, user: dict = Depends(auth.require_teacher_user)):
    """Teacher confirms (possibly edited) competency selection → creates preview."""
    form = await request.form()
    selected_ids = [int(v) for k, v in form.multi_items() if k == "competency_ids"]

    reqs = _get_test_requests()
    req = reqs.get(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Keine Kompetenzen ausgewählt")

    pid = _create_preview(req["student_name"], req["title"], selected_ids, request_id=req_id)
    return RedirectResponse(f"/tests/preview/{pid}", status_code=303)


@app.get("/tests/preview/{pid}", response_class=HTMLResponse)
async def test_preview(pid: str, request: Request, user: dict = Depends(auth.require_teacher_user)):
    preview = _TEST_PREVIEWS.get(pid)
    if not preview:
        raise HTTPException(status_code=404, detail="Vorschau nicht gefunden oder abgelaufen")
    return templates.TemplateResponse("test_preview.html", {
        "request": request, "user": user, "preview": preview,
    })


@app.post("/tests/finalize/{pid}")
async def finalize_test(pid: str, request: Request, user: dict = Depends(auth.require_teacher_user)):
    preview = _TEST_PREVIEWS.get(pid)
    if not preview:
        raise HTTPException(status_code=404, detail="Vorschau nicht gefunden oder abgelaufen")

    form = await request.form()
    questions = []
    for q in preview["questions"]:
        cid = q["competency_id"]
        text = form.get(f"question_{cid}", q["selected"])
        questions.append({"kid": str(cid), "text": text})

    if not questions:
        raise HTTPException(status_code=400, detail="Keine Fragen im Test")

    try:
        pdf_bytes = create_pdf(
            questions=questions,
            name=preview["student_name"],
            datum=date.today().strftime("%d.%m.%Y"),
            zusatzinfo=preview["title"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-Fehler: {e}")

    # Mark linked request as done
    req_id = preview.get("request_id")
    if req_id:
        db.update_test_request_status(req_id, "done")

    del _TEST_PREVIEWS[pid]

    safe_name = preview["student_name"].replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Kompetenznachweis.pdf"'},
    )


@app.get("/api/class-students/{class_id}")
async def api_class_students(class_id: str, user: dict = Depends(auth.require_teacher_user)):
    """AJAX: returns student list for a given class/group."""
    return [
        {"id": m["id"], "displayName": m["displayName"]}
        for m in db.get_class_members(class_id)
    ]


@app.get("/api/student-competencies")
async def api_student_competencies(student_id: str = "", user: dict = Depends(auth.require_teacher_user)):
    """AJAX: returns proven einfach competency IDs for a student (by object ID)."""
    if not student_id:
        return {"proven_einfach_ids": []}
    einfach_map, _, _, _ = _load_student_data(user["access_token"], student_id)
    proven_ids = [cid for cid, r in einfach_map.items() if r.get("achieved")]
    return {"proven_einfach_ids": proven_ids}


# ---------------------------------------------------------------------------
# Notenrechner
# ---------------------------------------------------------------------------

@app.get("/grades/calculator", response_class=HTMLResponse)
async def grade_calculator(request: Request, user: dict = Depends(auth.require_user)):
    active_ids = _load_active_ids(user["access_token"])
    record_map: dict = {}
    if not user["is_teacher"]:
        einfach_map, nachweise_by_comp, _, _ = _load_student_data(user["access_token"], user["oid"])
        for k in _EINFACH:
            r = einfach_map.get(k["id"])
            if r:
                record_map[k["id"]] = r
        for k in _NIVEAU:
            entries = nachweise_by_comp.get(k["id"], [])
            if entries:
                best = max(entries, key=lambda e: e.get("niveau_level", 0))
                record_map[k["id"]] = {"competency_id": k["id"], "niveau_level": best.get("niveau_level", 0), "achieved": False}
    return templates.TemplateResponse("grade_calculator.html", {
        "request": request, "user": user,
        "grade": None, "record_map": record_map,
        "active_ids": active_ids, "basis": "unterricht",
    })


@app.post("/grades/calculate", response_class=HTMLResponse)
async def calculate_grade_form(request: Request, user: dict = Depends(auth.require_user)):
    form = await request.form()
    basis = form.get("basis", "unterricht")
    active_ids = _load_active_ids(user["access_token"])

    records = []
    for k in _KOMPETENZEN:
        cid = k["id"]
        if k["typ"] == "einfach":
            achieved = form.get(f"achieved_{cid}") in ("on", "1", "true")
            records.append({"competency_id": cid, "achieved": achieved, "niveau_level": 0})
        else:
            niveau_level = int(form.get(f"niveau_{cid}", 0) or 0)
            records.append({"competency_id": cid, "achieved": False, "niveau_level": niveau_level})

    if basis == "unterricht" and active_ids:
        proven_ids = {r["competency_id"] for r in records
                      if r.get("achieved") or r.get("niveau_level", 0) > 0}
        comps = [k for k in _KOMPETENZEN if k["id"] in active_ids or k["id"] in proven_ids]
    else:
        comps = _KOMPETENZEN

    grade = calculate_grade(records, competencies=comps) if comps else None
    record_map = {r["competency_id"]: r for r in records}
    return templates.TemplateResponse("grade_calculator.html", {
        "request": request, "user": user,
        "grade": grade, "record_map": record_map,
        "active_ids": active_ids, "basis": basis,
        "no_active_warning": basis == "unterricht" and not active_ids,
    })


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

@app.get("/bookings", response_class=HTMLResponse)
async def bookings(request: Request, user: dict = Depends(auth.require_user)):
    return templates.TemplateResponse("bookings.html", {
        "request": request,
        "user": user,
        "use_bookings_api": settings.USE_BOOKINGS_API,
        "bookings_page_url": settings.BOOKINGS_PAGE_URL,
    })


# ---------------------------------------------------------------------------
# Admin: CSV-Upload + Listen-Verwaltung
# ---------------------------------------------------------------------------

@app.get("/admin/upload", response_class=HTMLResponse)
async def admin_upload(request: Request, user: dict = Depends(auth.require_teacher_user)):
    msg = request.query_params.get("msg", "")
    with_thema = sum(1 for k in _EINFACH if k.get("thema"))
    with_questions = sum(1 for k in _EINFACH if _QUESTIONS.get(str(k["id"])))
    return templates.TemplateResponse("upload.html", {
        "request": request, "user": user,
        "total_einfach": len(_EINFACH),
        "total_niveau": len(_NIVEAU),
        "with_thema": with_thema,
        "with_questions": with_questions,
        "msg": msg,
        "updated": request.query_params.get("updated", ""),
        "total_q": request.query_params.get("total", ""),
    })


@app.post("/admin/upload/kompetenzen")
async def upload_kompetenzen(
    file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    updated = 0
    for row in reader:
        try:
            cid = int(row.get("ID") or row.get("id") or 0)
        except (ValueError, TypeError):
            continue
        if cid <= 0:
            continue
        thema_raw = (row.get("Thema") or "").strip()
        thema_val = int(thema_raw) if thema_raw.isdigit() else None
        existing = _KOMPETENZ_MAP.get(cid)
        if existing:
            existing["name"] = (row.get("Kompetenz") or existing.get("name", "")).strip()
            existing["thema"] = thema_val
            existing["anmerkungen"] = (row.get("Anmerkungen") or "").strip()
            existing["bp_nummer"] = (row.get("BP-Nummer") or "").strip()
        else:
            _KOMPETENZEN.append({
                "id": cid,
                "typ": "einfach",
                "name": (row.get("Kompetenz") or "").strip(),
                "thema": thema_val,
                "anmerkungen": (row.get("Anmerkungen") or "").strip(),
                "bp_nummer": (row.get("BP-Nummer") or "").strip(),
            })
        updated += 1

    _KOMPETENZEN.sort(key=lambda k: k["id"])
    (BASE_DIR / "kompetenzen.json").write_text(
        json.dumps(_KOMPETENZEN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_kompetenzen()
    return RedirectResponse(f"/admin/upload?msg=kompetenzen_ok&updated={updated}", status_code=303)


@app.post("/admin/upload/questions")
async def upload_questions(
    file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    questions: dict[str, list[str]] = {}
    comp_ids: list[str] = []
    for row_num, row in enumerate(reader):
        if row_num == 0:
            # First row contains competency IDs for each column
            comp_ids = [cell.strip() for cell in row]
            continue
        for col_idx, cell in enumerate(row):
            if col_idx >= len(comp_ids):
                break
            cid = comp_ids[col_idx]
            if cid and cell.strip():
                questions.setdefault(cid, []).append(cell.strip())

    (BASE_DIR / "questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_questions()
    total = sum(len(v) for v in questions.values())
    return RedirectResponse(f"/admin/upload?msg=questions_ok&total={total}", status_code=303)


@app.post("/admin/upload/niveau")
async def upload_niveau(
    file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    """Parse pbK CSV (ID;Nummer;pbk;Möglichkeit1;Möglichkeit2;Möglichkeit3;Hinweise) and merge into kompetenzen.json."""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    updated = 0
    for row in reader:
        bp_nr = (row.get("Nummer") or "").strip()
        name = (row.get("pbk") or "").strip()
        if not name:
            continue
        moeglichkeiten = [
            m for m in [
                (row.get("Möglichkeit1") or "").strip(),
                (row.get("Möglichkeit2") or "").strip(),
                (row.get("Möglichkeit3") or "").strip(),
            ] if m
        ]
        anmerkungen = (row.get("Hinweise zu den Kriterien") or "").strip()

        # Merge by bp_nummer if it exists, otherwise by name match among niveau entries
        existing = None
        if bp_nr:
            existing = next((k for k in _KOMPETENZEN if k.get("bp_nummer") == bp_nr and k["typ"] == "niveau"), None)
        if existing is None:
            existing = next((k for k in _KOMPETENZEN if k["name"] == name and k["typ"] == "niveau"), None)

        if existing:
            existing["name"] = name
            existing["anmerkungen"] = anmerkungen
            if bp_nr:
                existing["bp_nummer"] = bp_nr
            existing["moeglichkeiten"] = moeglichkeiten
        else:
            new_id = max((k["id"] for k in _KOMPETENZEN), default=0) + 1
            _KOMPETENZEN.append({
                "id": new_id,
                "typ": "niveau",
                "name": name,
                "thema": None,
                "anmerkungen": anmerkungen,
                "bp_nummer": bp_nr,
                "moeglichkeiten": moeglichkeiten,
            })
        updated += 1

    _KOMPETENZEN.sort(key=lambda k: k["id"])
    (BASE_DIR / "kompetenzen.json").write_text(
        json.dumps(_KOMPETENZEN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_kompetenzen()
    return RedirectResponse(f"/admin/upload?msg=niveau_ok&updated={updated}", status_code=303)


@app.get("/admin/kompetenzen", response_class=HTMLResponse)
async def admin_kompetenzen_view(request: Request, user: dict = Depends(auth.require_teacher_user)):
    return templates.TemplateResponse("admin_kompetenzen.html", {
        "request": request, "user": user,
    })


@app.post("/admin/kompetenzen/save")
async def admin_kompetenzen_save(request: Request, user: dict = Depends(auth.require_teacher_user)):
    form = await request.form()
    for k in _KOMPETENZEN:
        cid = k["id"]
        name_val = form.get(f"name_{cid}")
        typ_val = form.get(f"typ_{cid}", "").strip()
        thema_raw = (form.get(f"thema_{cid}") or "").strip()
        anm_val = (form.get(f"anmerkungen_{cid}") or "").strip()
        if name_val is not None:
            k["name"] = name_val.strip()
        if typ_val in ("einfach", "niveau"):
            k["typ"] = typ_val
        k["thema"] = int(thema_raw) if thema_raw.isdigit() else None
        k["anmerkungen"] = anm_val
        # Möglichkeiten — only present for niveau rows in the form
        moeg_fields = [
            (form.get(f"moeg1_{cid}") or "").strip(),
            (form.get(f"moeg2_{cid}") or "").strip(),
            (form.get(f"moeg3_{cid}") or "").strip(),
        ]
        moeglichkeiten = [m for m in moeg_fields if m]
        if moeglichkeiten or k.get("typ") == "niveau":
            k["moeglichkeiten"] = moeglichkeiten

    (BASE_DIR / "kompetenzen.json").write_text(
        json.dumps(_KOMPETENZEN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_kompetenzen()
    return RedirectResponse("/admin/kompetenzen", status_code=303)


@app.post("/admin/kompetenzen/delete")
async def admin_kompetenzen_delete(
    comp_id: int = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    global _KOMPETENZEN
    _KOMPETENZEN = [k for k in _KOMPETENZEN if k["id"] != comp_id]
    (BASE_DIR / "kompetenzen.json").write_text(
        json.dumps(_KOMPETENZEN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_kompetenzen()
    return RedirectResponse("/admin/kompetenzen", status_code=303)


@app.post("/admin/kompetenzen/add")
async def admin_kompetenzen_add(
    typ: str = Form(...),
    name: str = Form(...),
    thema: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    if not name.strip():
        return RedirectResponse("/admin/kompetenzen", status_code=303)
    new_id = max((k["id"] for k in _KOMPETENZEN), default=0) + 1
    thema_val = int(thema) if thema.isdigit() else None
    entry: dict = {
        "id": new_id,
        "typ": typ if typ in ("einfach", "niveau") else "einfach",
        "name": name.strip(),
        "thema": thema_val,
        "anmerkungen": "",
    }
    if entry["typ"] == "niveau":
        entry["moeglichkeiten"] = []
    _KOMPETENZEN.append(entry)
    _KOMPETENZEN.sort(key=lambda k: k["id"])
    (BASE_DIR / "kompetenzen.json").write_text(
        json.dumps(_KOMPETENZEN, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_kompetenzen()
    anchor = "niveau" if entry["typ"] == "niveau" else "einfach"
    return RedirectResponse(f"/admin/kompetenzen#{anchor}", status_code=303)


@app.get("/admin/questions", response_class=HTMLResponse)
async def admin_questions_view(request: Request, user: dict = Depends(auth.require_teacher_user)):
    return templates.TemplateResponse("admin_questions.html", {
        "request": request, "user": user, "questions": _QUESTIONS,
    })


@app.post("/admin/questions/add")
async def admin_questions_add(
    comp_id: str = Form(...),
    text: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    if text.strip():
        _QUESTIONS.setdefault(comp_id, []).append(text.strip())
        (BASE_DIR / "questions.json").write_text(
            json.dumps(_QUESTIONS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _reload_questions()
    return RedirectResponse(f"/admin/questions#{comp_id}", status_code=303)


@app.post("/admin/questions/delete")
async def admin_questions_delete(
    comp_id: str = Form(...),
    index: int = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    lst = _QUESTIONS.get(comp_id, [])
    if 0 <= index < len(lst):
        lst.pop(index)
        if not lst:
            _QUESTIONS.pop(comp_id, None)
        (BASE_DIR / "questions.json").write_text(
            json.dumps(_QUESTIONS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _reload_questions()
    return RedirectResponse(f"/admin/questions#{comp_id}", status_code=303)


# ---------------------------------------------------------------------------
# Admin: Notenschlüssel
# ---------------------------------------------------------------------------

@app.get("/admin/grading-scale", response_class=HTMLResponse)
async def admin_grading_scale_page(request: Request, user: dict = Depends(auth.require_teacher_user)):
    msg = request.query_params.get("msg", "")
    presets = _get_all_presets()
    return templates.TemplateResponse("admin_grading_scale.html", {
        "request": request, "user": user,
        "scale": _GRADING_SCALE,
        "presets_json": json.dumps([
            {"id": p["id"], "label": p["label"],
             "scale": _parse_grade_scale_csv(p["file"])}
            for p in presets
        ]),
        "msg": msg,
    })


@app.post("/admin/grading-scale/save")
async def admin_grading_scale_save(
    request: Request, user: dict = Depends(auth.require_teacher_user)
):
    form = await request.form()
    new_scale = []
    for i, entry in enumerate(_GRADING_SCALE):
        try:
            pct = float(form.get(f"min_pct_{i}", entry["min_percent"]))
        except (ValueError, TypeError):
            pct = entry["min_percent"]
        new_scale.append({
            "note": entry["note"],
            "dezimal": entry.get("dezimal", 0.0),
            "min_percent": round(max(0.0, min(100.0, pct)), 1),
        })
    (BASE_DIR / "grading_scale.json").write_text(
        json.dumps(new_scale, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _reload_grading_scale()
    return RedirectResponse("/admin/grading-scale?msg=gespeichert", status_code=303)


@app.post("/admin/grading-scale/reset")
async def admin_grading_scale_reset(user: dict = Depends(auth.require_teacher_user)):
    p = BASE_DIR / "grading_scale.json"
    if p.exists():
        p.unlink()
    _reload_grading_scale()
    return RedirectResponse("/admin/grading-scale?msg=auf+Standard+zur%C3%BCckgesetzt", status_code=303)


@app.post("/admin/grading-scale/upload")
async def admin_grading_scale_upload(
    file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    content = await file.read()
    try:
        scale = _parse_grade_scale_bytes(content)
        if not scale:
            raise ValueError("Keine gültigen Einträge gefunden.")
    except Exception as e:
        return RedirectResponse(f"/admin/grading-scale?msg={quote(f'Fehler beim Parsen: {e}')}", status_code=303)

    note_50 = _note_at_50(scale)
    safe = _safe_note_filename(note_50)
    _GRADE_SCALES_DIR.mkdir(exist_ok=True)

    dest = _GRADE_SCALES_DIR / f"Note_{safe}.csv"
    v = 2
    while dest.exists():
        dest = _GRADE_SCALES_DIR / f"Note_{safe}_v{v}.csv"
        v += 1

    dest.write_bytes(content)
    msg = f"Hochgeladen: {dest.name} (50\u2009% \u2192 Note {note_50})"
    return RedirectResponse(f"/admin/grading-scale?msg={quote(msg)}", status_code=303)


# ---------------------------------------------------------------------------
# Admin: Klassenverwaltung (local SQLite — no Azure group permissions needed)
# ---------------------------------------------------------------------------

@app.get("/admin/classes", response_class=HTMLResponse)
async def admin_classes(request: Request, user: dict = Depends(auth.require_teacher_user)):
    classes = db.get_classes_with_counts()
    return templates.TemplateResponse("admin_classes.html", {
        "request": request, "user": user, "classes": classes,
        "msg": request.query_params.get("msg", ""),
    })


@app.post("/admin/classes/add")
async def admin_classes_add(
    name: str = Form(...),
    description: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    if name.strip():
        db.add_class(name.strip(), description.strip())
    return RedirectResponse("/admin/classes", status_code=303)


@app.post("/admin/classes/delete")
async def admin_classes_delete(
    class_id: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    db.delete_class(class_id)
    return RedirectResponse("/admin/classes", status_code=303)


@app.get("/admin/classes/{class_id}", response_class=HTMLResponse)
async def admin_class_members(
    class_id: str,
    request: Request,
    user: dict = Depends(auth.require_teacher_user),
):
    classes = db.get_classes()
    cls = next((c for c in classes if c["id"] == class_id), None)
    if not cls:
        raise HTTPException(status_code=404, detail="Klasse nicht gefunden")
    members = db.get_class_members(class_id)
    return templates.TemplateResponse("admin_class_members.html", {
        "request": request, "user": user, "cls": cls, "members": members,
        "msg": request.query_params.get("msg", ""),
    })


@app.post("/admin/classes/{class_id}/members/add")
async def admin_class_member_add(
    class_id: str,
    student_name: str = Form(...),
    upn: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    if student_name.strip():
        sid = upn.strip() or student_name.strip()
        db.add_class_member(class_id, sid, student_name.strip(), upn.strip())
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=303)


@app.post("/admin/classes/{class_id}/members/delete")
async def admin_class_member_delete(
    class_id: str,
    student_id: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    db.delete_class_member(class_id, student_id)
    return RedirectResponse(f"/admin/classes/{class_id}", status_code=303)


@app.post("/admin/classes/{class_id}/members/import")
async def admin_class_members_import(
    class_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    # Try semicolon first, then comma
    delimiter = ";" if ";" in text.split("\n")[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    count = db.import_class_members_csv(class_id, list(reader))
    return RedirectResponse(
        f"/admin/classes/{class_id}?msg={quote(f'{count} Schüler:innen importiert')}",
        status_code=303,
    )
