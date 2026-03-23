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


def _load_competency_list(list_id: str, list_source: str = "system") -> tuple[list[dict], dict]:
    """Load a specific competency list by ID.
    
    Args:
        list_id: The list ID
        list_source: "system" (from files) or "teacher" (from DB)
    """
    if list_source == "teacher":
        # Load from teacher_lists table
        teacher_list = db.get_teacher_list(list_id)
        if not teacher_list:
            raise FileNotFoundError(f"Lehrer-Liste nicht gefunden: {list_id}")
        
        data = teacher_list["data"]
        competencies = data.get("competencies", [])
        questions = teacher_list.get("questions", {})
        return competencies, questions
    
    else:  # system
        list_file = BASE_DIR / "kompetenzlisten" / f"{list_id}.json"
        if not list_file.exists():
            raise FileNotFoundError(f"Kompetenzliste nicht gefunden: {list_id}")
        
        data = json.loads(list_file.read_text(encoding="utf-8"))
        competencies = data.get("competencies", [])
        
        # Load questions if available
        questions_file = BASE_DIR / "kompetenzlisten" / f"{list_id}-questions.json"
        if questions_file.exists():
            questions = json.loads(questions_file.read_text(encoding="utf-8"))
        else:
            questions = {}
        
        return competencies, questions


def _reload_kompetenzen() -> None:
    """Load default list (class 9) for backward compatibility during transition."""
    global _KOMPETENZEN, _KOMPETENZ_MAP, _EINFACH, _NIVEAU, _QUESTIONS
    
    # Load default list (class 9)
    _KOMPETENZEN, _QUESTIONS = _load_competency_list("klasse-9-chemie")
    
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
    # Set globals as defaults (will be overridden in Dashboard for class-specific)
    templates.env.globals["einfach_kompetenzen"] = _EINFACH
    templates.env.globals["niveau_kompetenzen"]  = _NIVEAU
    templates.env.globals["einfach_nach_thema"]  = themen


def _reload_questions() -> None:
    """Questions are now loaded together with competencies."""
    pass  # Handled in _reload_kompetenzen


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

# Dev-Mode Users
DEV_STUDENT_OID_9   = "anna@schule.de"
DEV_STUDENT_NAME_9  = "Anna Beispiel"
DEV_STUDENT_OID_10  = "max@schule.de"
DEV_STUDENT_NAME_10 = "Max Mustermann"


def _init_dev_db() -> None:
    """Pre-populate SQLite with sample data when in DEV_MODE and DB is empty."""
    if not settings.DEV_MODE:
        return
    # Only populate once — skip if already initialized
    if db.get_einfach_records(DEV_STUDENT_OID_9):
        return

    # Klasse 9
    db.add_class(
        "9a (Dev)", "Beispielklasse Klasse 9", 
        class_id="dev-class-9",
        grade_level=9,
        competency_list_id="klasse-9-chemie",
        list_source="system"
    )
    db.add_class_member("dev-class-9", DEV_STUDENT_OID_9, DEV_STUDENT_NAME_9, DEV_STUDENT_OID_9)

    # Klasse 10
    db.add_class(
        "10a (Dev)", "Beispielklasse Klasse 10",
        class_id="dev-class-10", 
        grade_level=10,
        competency_list_id="klasse-10-chemie",
        list_source="system"
    )
    db.add_class_member("dev-class-10", DEV_STUDENT_OID_10, DEV_STUDENT_NAME_10, DEV_STUDENT_OID_10)

    # Unterrichtsstand Klasse 9: einfach Themen 1–3 + first 10 niveau
    # Load Klasse 9 competencies
    comps_9, _ = _load_competency_list("klasse-9-chemie", "system")
    einfach_9 = [c for c in comps_9 if c["typ"] == "einfach"]
    niveau_9 = [c for c in comps_9 if c["typ"] == "niveau"]
    active_einfach_9 = [k for k in einfach_9 if k.get("thema") in (1, 2, 3)]
    active_niveau_9 = niveau_9[:10]
    db.set_active_ids({k["id"] for k in active_einfach_9} | {k["id"] for k in active_niveau_9}, class_id="dev-class-9")
    
    # Unterrichtsstand Klasse 10: first 30 einfach + first 10 niveau
    comps_10, _ = _load_competency_list("klasse-10-chemie", "system")
    einfach_10 = [c for c in comps_10 if c["typ"] == "einfach"]
    niveau_10 = [c for c in comps_10 if c["typ"] == "niveau"]
    active_einfach_10 = einfach_10[:30]
    active_niveau_10 = niveau_10[:10]
    db.set_active_ids({k["id"] for k in active_einfach_10} | {k["id"] for k in active_niveau_10}, class_id="dev-class-10")

    # Anna (Klasse 9): 80% der einfach erreicht
    n_achieved = round(len(active_einfach_9) * 0.8)
    for k in active_einfach_9:
        db.upsert_einfach(
            DEV_STUDENT_OID_9, DEV_STUDENT_NAME_9, k["id"],
            achieved=(k in active_einfach_9[:n_achieved]),
            updated_by="lehrer@schule.de",
        )

    # Anna niveau: 5×Advanced, 3×Beginner, 2×Expert
    for k, lvl in zip(active_niveau_9, [2, 2, 2, 2, 2, 1, 1, 1, 3, 3]):
        db.add_nachweis(
            DEV_STUDENT_OID_9, DEV_STUDENT_NAME_9, k["id"], lvl,
            "https://example.com/nachweis", "Beispiel-Nachweis",
            "lehrer@schule.de",
        )

    # Max (Klasse 10): 60% erreicht
    n_achieved_10 = round(len(active_einfach_10) * 0.6)
    for k in active_einfach_10:
        db.upsert_einfach(
            DEV_STUDENT_OID_10, DEV_STUDENT_NAME_10, k["id"],
            achieved=(k in active_einfach_10[:n_achieved_10]),
            updated_by="lehrer@schule.de",
        )

    # Max niveau: 3×Advanced, 4×Beginner, 3×Expert
    for k, lvl in zip(active_niveau_10, [2, 2, 2, 1, 1, 1, 1, 3, 3, 3]):
        db.add_nachweis(
            DEV_STUDENT_OID_10, DEV_STUDENT_NAME_10, k["id"], lvl,
            "https://example.com/nachweis", "Nachweis Max",
            "lehrer@schule.de",
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


def _create_preview(student_name: str, title: str, competency_ids: list,
                    request_id: str | None = None, class_id: str | None = None) -> str:
    # Load questions from class-specific list if available
    questions_dict = _QUESTIONS.copy()
    if class_id:
        cls = db.get_class(class_id)
        if cls:
            einfach_list_id = cls.get("einfach_list_id") or cls.get("competency_list_id")
            einfach_list_source = cls.get("einfach_list_source") or cls.get("list_source", "system")
            if einfach_list_id:
                if einfach_list_source == "teacher":
                    # Load questions from teacher list
                    teacher_list = db.get_teacher_list(einfach_list_id)
                    if teacher_list and teacher_list.get("questions"):
                        questions_dict = teacher_list["questions"]
                else:
                    # Load questions from system list (JSON file)
                    try:
                        _, system_questions = _load_competency_list(einfach_list_id, "system")
                        if system_questions:
                            questions_dict = system_questions
                    except FileNotFoundError:
                        pass
    
    questions = []
    for cid in competency_ids:
        k = _KOMPETENZ_MAP.get(cid)
        if not k or k["typ"] != "einfach":
            continue
        opts = questions_dict.get(str(cid)) or [k["name"]]
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


def _build_grade_records(einfach_map: dict, nachweise_by_comp: dict, 
                         competencies: list[dict] | None = None) -> list[dict]:
    """Merge einfach records + best-niveau-per-comp into a unified list for calculate_grade().
    If competencies is None, uses _KOMPETENZEN (fallback for backward compatibility)."""
    comps = competencies if competencies is not None else _KOMPETENZEN
    records = []
    for k in comps:
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
    logout_msg = request.query_params.get("logout") == "1"
    if settings.DEV_MODE:
        return templates.TemplateResponse("dev_login.html", {"request": request, "logout_msg": logout_msg})
    state = secrets.token_hex(16)
    url = auth.get_auth_url(state, request)
    return RedirectResponse(url)


@app.post("/dev-login")
async def dev_login(
    display_name: str = Form(...),
    role: str = Form(...),
    email: str = Form(default=""),
):
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="Nur im Dev-Modus verfügbar")
    is_teacher = role == "teacher"
    
    # Bestimme UPN basierend auf Rolle und optionaler Email
    if is_teacher:
        upn = "lehrer@schule.de"
    else:
        # Student: use provided email or default
        if email:
            upn = email
        elif "anna" in display_name.lower():
            upn = "anna@schule.de"
        elif "max" in display_name.lower():
            upn = "max@schule.de"
        else:
            upn = "student@schule.de"
    
    user_info = {
        "oid": upn,
        "upn": upn,
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
        token_response = auth.exchange_code(code, request)
    except ValueError as e:
        return HTMLResponse(f"<h1>Token-Fehler</h1><p>{e}</p>", status_code=400)
    user_info = auth.build_user_info(token_response)
    response = RedirectResponse(url="/teacher" if user_info["is_teacher"] else "/", status_code=302)
    auth.set_session(response, user_info)
    return response


@app.post("/logout")
async def logout(request: Request):
    # Build the post-logout redirect URL
    netloc = request.url.netloc
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto
    elif netloc.startswith("localhost") or netloc.startswith("127."):
        scheme = "http"
    else:
        scheme = "https"
    post_logout_uri = f"{scheme}://{netloc}/login?logout=1"
    
    # Get Microsoft logout URL (or local /login in DEV_MODE)
    logout_url = auth.get_logout_url(post_logout_uri)
    
    response = RedirectResponse(url=logout_url, status_code=302)
    auth.clear_session(response)
    return response


@app.get("/auth/me")
async def auth_me(user: dict = Depends(auth.require_user)):
    return {"oid": user["oid"], "upn": user["upn"],
            "display_name": user["display_name"], "is_teacher": user["is_teacher"]}


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

def _get_student_competencies(student_id: str) -> tuple[list[dict], list[dict], set[int], str | None]:
    """Get competencies for a student based on their class.
    Returns: (einfach_list, niveau_list, active_ids, class_id)"""
    student_class = db.get_student_class(student_id)
    
    if not student_class:
        # Fallback to default list (class 9)
        return _EINFACH, _NIVEAU, db.get_active_ids(), None
    
    class_id = student_class["id"]
    
    # Use new separate lists if available, otherwise fall back to legacy
    einfach_list_id = student_class.get("einfach_list_id") or student_class.get("competency_list_id")
    einfach_list_source = student_class.get("einfach_list_source") or student_class.get("list_source", "system")
    niveau_list_id = student_class.get("niveau_list_id") or student_class.get("competency_list_id")
    niveau_list_source = student_class.get("niveau_list_source") or student_class.get("list_source", "system")
    
    if not einfach_list_id and not niveau_list_id:
        # Fallback to default list (class 9)
        return _EINFACH, _NIVEAU, db.get_active_ids(), None
    
    try:
        einfach = []
        niveau = []
        
        # Load einfach list
        if einfach_list_id:
            comps, _ = _load_competency_list(einfach_list_id, einfach_list_source)
            einfach = sorted([c for c in comps if c["typ"] == "einfach"], 
                            key=lambda k: (k.get("thema") or 999, k["id"]))
        
        # Load niveau list
        if niveau_list_id:
            comps, _ = _load_competency_list(niveau_list_id, niveau_list_source)
            niveau = sorted([c for c in comps if c["typ"] == "niveau"], key=lambda k: k["id"])
        
        active_ids = db.get_active_ids(class_id)
        return einfach, niveau, active_ids, class_id
    except FileNotFoundError:
        # Fallback if list file not found
        return _EINFACH, _NIVEAU, db.get_active_ids(), None


@app.get("/", response_class=HTMLResponse)
async def student_dashboard(request: Request, user: dict = Depends(auth.require_user)):
    if user["is_teacher"]:
        return RedirectResponse("/teacher")

    einfach_map, nachweise_by_comp, best_nachweis_by_comp, _ = _load_student_data(
        user["access_token"], user["oid"]
    )
    
    # Get class-specific competencies
    class_einfach, class_niveau, active_ids, class_id = _get_student_competencies(user["oid"])
    
    # Build competency lookup for this class
    class_comp_ids = {c["id"] for c in class_einfach + class_niveau}
    
    # Filter records to only include class competencies
    einfach_map_filtered = {k: v for k, v in einfach_map.items() if k in class_comp_ids}
    nachweise_filtered = {k: v for k, v in nachweise_by_comp.items() if k in class_comp_ids}
    best_nachweis_filtered = {k: v for k, v in best_nachweis_by_comp.items() if k in class_comp_ids}

    # Recalculate grade filtered by active_ids + proven competencies
    if active_ids:
        proven_ids = (
            {cid for cid, r in einfach_map_filtered.items() if r.get("achieved")}
            | {cid for cid, entries in nachweise_filtered.items()
               if any(e.get("niveau_level", 0) > 0 for e in entries)}
        )
        grade_comps = [k for k in class_einfach + class_niveau 
                      if k["id"] in active_ids or k["id"] in proven_ids]
    else:
        proven_ids = set()
        grade_comps = None
    
    # Use class-specific competencies for grade calculation
    class_comps = class_einfach + class_niveau
    grade = calculate_grade(_build_grade_records(einfach_map_filtered, nachweise_filtered, class_comps), 
                           competencies=grade_comps if grade_comps else class_comps)

    # JSON payloads for client-side planning mode (filtered to class competencies)
    kompetenzen_json = json.dumps([{"id": k["id"], "typ": k["typ"]} for k in class_einfach + class_niveau])
    current_state: dict = {}
    for k in class_einfach:
        r = einfach_map_filtered.get(k["id"], {})
        current_state[k["id"]] = {"achieved": bool(r.get("achieved")), "niveau_level": 0}
    for k in class_niveau:
        entries = nachweise_filtered.get(k["id"], [])
        best_niv = max((e.get("niveau_level", 0) for e in entries), default=0)
        current_state[k["id"]] = {"achieved": False, "niveau_level": best_niv}
    current_state_json = json.dumps(current_state)
    active_ids_list = json.dumps(sorted(active_ids))
    proven_ids_list = json.dumps(sorted(proven_ids)) if active_ids else "[]"
    grading_scale_json = json.dumps(
        [{"note": e["note"], "min_percent": e["min_percent"]} for e in _GRADING_SCALE]
    )

    # Build antrag lookup dicts for this student (filtered to class competencies)
    pending_antraege_by_comp: dict[str, dict] = {}
    rejected_niveau_antraege_by_comp: dict[str, dict] = {}
    for a in db.get_all_kompetenzantraege().values():
        if a["student_id"] != user["oid"]:
            continue
        # competency_id is now always a string (e.901, n.989)
        cid = a["competency_id"]
        if cid not in class_comp_ids:
            continue  # Skip antraege for competencies not in this class
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
        "einfach_map": einfach_map_filtered,
        "nachweise_by_comp": nachweise_filtered,
        "best_nachweis_by_comp": best_nachweis_filtered,
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
        "class_id": class_id,
        "einfach_kompetenzen": class_einfach,  # Override global
        "niveau_kompetenzen": class_niveau,    # Override global
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
    # Get student's class competencies
    class_einfach, class_niveau, active_ids, _ = _get_student_competencies(student_id)
    
    # Load student data
    einfach_map, nachweise_by_comp, best_nachweis_by_comp, _ = _load_student_data(
        user["access_token"], student_id
    )
    
    # Filter to class-specific competencies
    class_comp_ids = {c["id"] for c in class_einfach + class_niveau}
    einfach_map_filtered = {k: v for k, v in einfach_map.items() if k in class_comp_ids}
    nachweise_filtered = {k: v for k, v in nachweise_by_comp.items() if k in class_comp_ids}
    
    # Calculate grade with class-specific competencies
    class_comps = class_einfach + class_niveau
    if active_ids:
        proven_ids = (
            {cid for cid, r in einfach_map_filtered.items() if r.get("achieved")}
            | {cid for cid, entries in nachweise_filtered.items()
               if any(e.get("niveau_level", 0) > 0 for e in entries)}
        )
        grade_comps = [k for k in class_comps if k["id"] in active_ids or k["id"] in proven_ids]
    else:
        grade_comps = None
    
    grade = calculate_grade(
        _build_grade_records(einfach_map_filtered, nachweise_filtered, class_comps),
        competencies=grade_comps if grade_comps else class_comps
    )
    
    # JSON payloads for client-side planning mode (class-specific)
    kompetenzen_json = json.dumps([{"id": k["id"], "typ": k["typ"]} for k in class_einfach + class_niveau])
    current_state: dict = {}
    for k in class_einfach:
        r = einfach_map_filtered.get(k["id"], {})
        current_state[k["id"]] = {"achieved": bool(r.get("achieved")), "niveau_level": 0}
    for k in class_niveau:
        entries = nachweise_filtered.get(k["id"], [])
        best_niv = max((e.get("niveau_level", 0) for e in entries), default=0)
        current_state[k["id"]] = {"achieved": False, "niveau_level": best_niv}
    current_state_json = json.dumps(current_state)
    active_ids_list = json.dumps(sorted(active_ids))
    grading_scale_json = json.dumps(
        [{"note": e["note"], "min_percent": e["min_percent"]} for e in _GRADING_SCALE]
    )
    
    return templates.TemplateResponse("student_detail.html", {
        "request": request,
        "user": user,
        "student_id": student_id,
        "student_name": student_name,
        "class_id": class_id,
        "einfach_map": einfach_map_filtered,  # Use filtered
        "nachweise_by_comp": nachweise_filtered,  # Use filtered
        "best_nachweis_by_comp": {k: v for k, v in best_nachweis_by_comp.items() if k in class_comp_ids},
        "grade": grade,
        "active_ids": active_ids,
        "einfach_kompetenzen": class_einfach,  # Use class-specific
        "niveau_kompetenzen": class_niveau,    # Use class-specific
        "kompetenzen_json": kompetenzen_json,
        "active_ids_list": active_ids_list,
        "current_state_json": current_state_json,
        "grading_scale_json": grading_scale_json,
    })


@app.post("/records/update")
async def update_record(
    student_id: str = Form(...),
    student_name: str = Form(...),
    competency_id: str = Form(...),  # Format: e.901, n.989
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
    competency_id: str = Form(...),  # Format: e.901, n.989
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


@app.post("/records/nachweis/delete")
async def delete_nachweis(
    nachweis_id: str = Form(...),
    student_id: str = Form(...),
    student_name: str = Form(...),
    class_id: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    db.delete_nachweis(nachweis_id)
    return RedirectResponse(
        url=f"/teacher/student/{student_id}?class_id={class_id}&student_name={student_name}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Teacher competency list management
# ---------------------------------------------------------------------------

@app.get("/teacher/competency-lists", response_class=HTMLResponse)
async def teacher_competency_lists(
    request: Request,
    user: dict = Depends(auth.require_teacher_user),
):
    # Get system lists from kompetenzlisten/ directory
    system_lists = []
    kompetenzlisten_dir = BASE_DIR / "kompetenzlisten"
    if kompetenzlisten_dir.exists():
        for f in sorted(kompetenzlisten_dir.glob("*.json")):
            if f.name.endswith("-questions.json"):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                # Check if system questions exist
                questions_file = kompetenzlisten_dir / f"{f.stem}-questions.json"
                has_questions = questions_file.exists()
                # System lists contain both types - mark as None or 'both'
                # We'll handle them specially in the template
                einfach_count = len([c for c in data.get("competencies", []) if c.get("typ") == "einfach"])
                niveau_count = len([c for c in data.get("competencies", []) if c.get("typ") == "niveau"])
                system_lists.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "grade_level": data.get("grade_level", 0),
                    "competency_count": len(data.get("competencies", [])),
                    "einfach_count": einfach_count,
                    "niveau_count": niveau_count,
                    "has_system_questions": has_questions,
                    "typ": "both",  # Special marker for system lists
                })
            except Exception:
                pass
    
    # Get teacher's own uploaded lists
    teacher_lists = db.get_teacher_lists(uploaded_by=user["upn"])
    
    # Get classes for assignment
    classes = db.get_classes_with_counts()
    
    return templates.TemplateResponse("teacher_competency_lists.html", {
        "request": request,
        "user": user,
        "system_lists": system_lists,
        "teacher_lists": teacher_lists,
        "classes": classes,
    })


def _parse_csv_competencies(content: bytes, typ: str, grade_level: int) -> list[dict]:
    """Parse CSV content and return competencies list.
    
    Args:
        content: CSV file content as bytes
        typ: "einfach" or "niveau"
        grade_level: grade level (9, 10, etc.)
    """
    import csv
    import io
    
    # Parse CSV
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    
    competencies = []
    for row in reader:
        if not row.get('ID'):
            continue
        
        try:
            comp_id = int(row['ID'])
        except (ValueError, TypeError):
            continue
        
        # New ID format: {typ}.{grade_level}{id:02d}
        # e.g., Klasse 9, Einfach, ID 1 -> "e.901"
        # e.g., Klasse 10, Niveau, ID 1 -> "n.1001"
        prefix = "n" if typ == "niveau" else "e"
        adjusted_id = f"{prefix}.{grade_level}{comp_id:02d}"
        
        if typ == "einfach":
            competency = {
                "id": adjusted_id,
                "typ": "einfach",
                "name": row.get('Kompetenz', '').strip(),
                "thema": int(row['Thema']) if row.get('Thema') and row['Thema'].strip() else None,
                "anmerkungen": row.get('Anmerkungen', '').strip(),
            }
        else:  # niveau
            moeglichkeiten = []
            for i in range(1, 4):
                val = row.get(f'Möglichkeit{i}', '').strip()
                if val:
                    moeglichkeiten.append(val)
            
            competency = {
                "id": adjusted_id,
                "typ": "niveau",
                "name": row.get('pbk', '').strip(),
                "bp_nummer": row.get('Nummer', '').strip(),
                "moeglichkeiten": moeglichkeiten,
                "anmerkungen": row.get('Hinweise zu den Kriterien', '').strip(),
            }
        
        competencies.append(competency)
    
    return competencies


def _parse_questions(content: bytes) -> dict:
    """Parse questions from various CSV formats or JSON.
    
    Supported formats:
    1. JSON: {"e.901": ["Frage 1", "Frage 2"]}
    2. CSV (row-based): competency_id;frage\ne.901;Frage 1
    3. CSV (column-based): 1;2;3...\nFrage1;Frage2;Frage3... (questions per competency in columns)
    """
    import csv
    import io
    import json
    
    text = content.decode('utf-8-sig').strip()
    
    # Try JSON first (starts with { or [)
    if text.startswith('{') or text.startswith('['):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {k: v if isinstance(v, list) else [v] for k, v in data.items()}
            return {}
        except json.JSONDecodeError:
            pass
    
    # Try CSV formats
    lines = text.split('\n')
    if not lines:
        return {}
    
    first_line = lines[0].strip()
    
    # Check if first line is header with column numbers (column-based format)
    if first_line and first_line[0].isdigit() and ';' in first_line:
        # Column-based format: questions are in columns
        # First line: "1;2;3;4..."
        # Following lines: "Question1;Question2;Question3..."
        questions = {}
        reader = csv.reader(io.StringIO(text), delimiter=';')
        rows = list(reader)
        
        if len(rows) >= 2:
            # Build competency IDs from column positions (e.901, e.902, etc.)
            for col_idx in range(len(rows[0])):
                comp_id = f"e.{901 + col_idx}"  # Start with e.901
                col_questions = []
                for row in rows[1:]:  # Skip header row with numbers
                    if col_idx < len(row) and row[col_idx].strip():
                        col_questions.append(row[col_idx].strip())
                if col_questions:
                    questions[comp_id] = col_questions
        return questions
    
    # Try row-based CSV format with headers
    questions = {}
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=';')
        for row in reader:
            comp_id = row.get('competency_id', '').strip()
            frage = row.get('frage', '').strip()
            if comp_id and frage:
                if comp_id not in questions:
                    questions[comp_id] = []
                questions[comp_id].append(frage)
    except Exception:
        pass
    
    return questions


@app.post("/teacher/competency-lists/upload")
async def teacher_competency_lists_upload(
    request: Request,
    name: str = Form(...),
    typ: str = Form(...),
    grade_level: int = Form(...),
    file: UploadFile = File(...),
    questions_file: UploadFile = File(None),
    user: dict = Depends(auth.require_teacher_user),
):
    print(f"DEBUG UPLOAD: name={name}, typ={typ}, grade_level={grade_level}", flush=True)
    print(f"DEBUG UPLOAD: questions_file={questions_file}", flush=True)
    print(f"DEBUG UPLOAD: questions_file.filename={questions_file.filename if questions_file else 'None'}", flush=True)
    
    # Validate typ
    if typ not in ("einfach", "niveau"):
        raise HTTPException(status_code=400, detail="Typ muss 'einfach' oder 'niveau' sein")
    
    # Parse competencies CSV
    content = await file.read()
    try:
        competencies = _parse_csv_competencies(content, typ, grade_level)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Parsen der CSV: {e}")
    
    data = {
        "name": name,
        "grade_level": grade_level,
        "typ": typ,
        "competencies": competencies,
    }
    
    # Load questions if provided
    questions = {}
    if questions_file and questions_file.filename and len(questions_file.filename) > 0:
        print(f"DEBUG UPLOAD: Reading questions_file...", flush=True)
        questions_content = await questions_file.read()
        print(f"DEBUG UPLOAD: questions_content length={len(questions_content)}", flush=True)
        if questions_content and len(questions_content) > 0:
            try:
                questions = _parse_questions(questions_content)
                print(f"DEBUG UPLOAD: Parsed {len(questions)} question entries", flush=True)
            except Exception as e:
                print(f"DEBUG UPLOAD: Parse error: {e}", flush=True)
                raise HTTPException(status_code=400, detail=f"Fehler beim Parsen der Fragen-CSV: {e}")
    else:
        print(f"DEBUG UPLOAD: No questions file provided", flush=True)
    
    # Generate ID
    list_id = f"teacher-{user['upn'].replace('@', '-').replace('.', '-')}-{grade_level}-{int(datetime.now().timestamp())}"
    
    # Save to DB
    db.save_teacher_list(
        list_id=list_id,
        name=name,
        grade_level=grade_level,
        uploaded_by=user["upn"],
        data=data,
        questions=questions,
        typ=typ,
    )
    
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.post("/teacher/competency-lists/{list_id}/upload-questions")
async def teacher_competency_lists_upload_questions(
    list_id: str,
    questions_file: UploadFile = File(...),
    user: dict = Depends(auth.require_teacher_user),
):
    import logging
    logger = logging.getLogger(__name__)
    
    # Get existing list
    teacher_list = db.get_teacher_list(list_id)
    if not teacher_list or teacher_list["uploaded_by"] != user["upn"]:
        raise HTTPException(status_code=403, detail="Nicht berechtigt")
    
    # Debug logging
    logger.error(f"DEBUG: Upload questions for list {list_id}")
    logger.error(f"DEBUG: questions_file = {questions_file}")
    logger.error(f"DEBUG: questions_file.filename = {questions_file.filename if questions_file else 'None'}")
    
    # Parse questions CSV
    questions_content = await questions_file.read()
    logger.error(f"DEBUG: questions_content length = {len(questions_content) if questions_content else 0}")
    try:
        questions = _parse_questions(questions_content)
        logger.error(f"DEBUG: Parsed {len(questions)} question entries")
    except Exception as e:
        logger.error(f"DEBUG: Parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Fehler beim Parsen der CSV: {e}")
    
    # Update list with questions
    db.save_teacher_list(
        list_id=list_id,
        name=teacher_list["name"],
        grade_level=teacher_list["grade_level"],
        uploaded_by=user["upn"],
        data=teacher_list["data"],
        questions=questions,
        typ=teacher_list.get("typ", "einfach"),
    )
    
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.post("/teacher/competency-lists/{list_id}/use-system-questions")
async def teacher_competency_lists_use_system_questions(
    list_id: str,
    user: dict = Depends(auth.require_teacher_user),
):
    # Get existing list
    teacher_list = db.get_teacher_list(list_id)
    if not teacher_list or teacher_list["uploaded_by"] != user["upn"]:
        raise HTTPException(status_code=403, detail="Nicht berechtigt")
    
    # Try to find matching system questions (JSON format in kompetenzlisten/)
    grade_level = teacher_list["grade_level"]
    system_questions_file = BASE_DIR / "kompetenzlisten" / f"klasse-{grade_level}-chemie-questions.json"
    
    questions = {}
    if system_questions_file.exists():
        questions = json.loads(system_questions_file.read_text(encoding="utf-8"))
    else:
        # Try to parse from _samples CSV
        samples_dir = BASE_DIR / "_samples"
        questions_csv = samples_dir / f"Testfragen_{grade_level}_alle.csv"
        if questions_csv.exists():
            try:
                content = questions_csv.read_bytes()
                questions = _parse_questions(content)
            except Exception:
                pass
    
    # Update list with system questions
    db.save_teacher_list(
        list_id=list_id,
        name=teacher_list["name"],
        grade_level=teacher_list["grade_level"],
        uploaded_by=user["upn"],
        data=teacher_list["data"],
        questions=questions,
        typ=teacher_list.get("typ", "einfach"),
    )
    
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.post("/teacher/competency-lists/delete")
async def teacher_competency_lists_delete(
    list_id: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    success = db.delete_teacher_list(list_id, uploaded_by=user["upn"])
    if not success:
        raise HTTPException(status_code=403, detail="Nicht berechtigt oder Liste nicht gefunden")
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.post("/teacher/class/{class_id}/set-list")
async def teacher_class_set_list(
    class_id: str,
    list_id: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    # Legacy endpoint - sets both einfach and niveau to the same list
    # Determine if this is a system or teacher list
    kompetenzlisten_dir = BASE_DIR / "kompetenzlisten"
    system_list_file = kompetenzlisten_dir / f"{list_id}.json"
    
    if system_list_file.exists():
        list_source = "system"
    else:
        # Check if it's a teacher list
        teacher_list = db.get_teacher_list(list_id)
        if not teacher_list:
            raise HTTPException(status_code=404, detail="Liste nicht gefunden")
        list_source = "teacher"
    
    db.set_class_competency_list(class_id, list_id, list_source)
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.post("/teacher/class/{class_id}/set-lists")
async def teacher_class_set_lists(
    class_id: str,
    einfach_list_id: str = Form(...),
    niveau_list_id: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    """Set separate einfach and niveau competency lists for a class."""
    
    def get_list_source(list_id: str) -> str:
        kompetenzlisten_dir = BASE_DIR / "kompetenzlisten"
        system_list_file = kompetenzlisten_dir / f"{list_id}.json"
        if system_list_file.exists():
            return "system"
        teacher_list = db.get_teacher_list(list_id)
        if not teacher_list:
            raise HTTPException(status_code=404, detail=f"Liste {list_id} nicht gefunden")
        return "teacher"
    
    einfach_source = get_list_source(einfach_list_id)
    niveau_source = get_list_source(niveau_list_id)
    
    db.set_class_competency_lists(
        class_id,
        einfach_list_id, einfach_source,
        niveau_list_id, niveau_source
    )
    return RedirectResponse("/teacher/competency-lists", status_code=302)


@app.get("/teacher/competency-lists/{list_id}/edit", response_class=HTMLResponse)
async def teacher_competency_list_edit(
    list_id: str,
    request: Request,
    user: dict = Depends(auth.require_teacher_user),
):
    """Show edit page for a teacher-uploaded competency list."""
    teacher_list = db.get_teacher_list(list_id)
    if not teacher_list:
        raise HTTPException(status_code=404, detail="Liste nicht gefunden")
    
    # Verify ownership
    if teacher_list["uploaded_by"] != user["upn"]:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    
    return templates.TemplateResponse("teacher_list_edit.html", {
        "request": request,
        "user": user,
        "list": teacher_list,
    })


@app.post("/teacher/competency-lists/{list_id}/update")
async def teacher_competency_list_update(
    list_id: str,
    request: Request,
    user: dict = Depends(auth.require_teacher_user),
):
    """Update a teacher-uploaded competency list."""
    teacher_list = db.get_teacher_list(list_id)
    if not teacher_list:
        raise HTTPException(status_code=404, detail="Liste nicht gefunden")
    
    # Verify ownership
    if teacher_list["uploaded_by"] != user["upn"]:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    
    form = await request.form()
    
    # Build competencies from form data
    name = form.get("name", teacher_list["name"])
    grade_level = int(form.get("grade_level", teacher_list["grade_level"]))
    typ = form.get("typ", teacher_list["typ"])
    
    competencies = []
    comp_index = 0
    while f"comp_{comp_index}_id" in form:
        comp_id = int(form[f"comp_{comp_index}_id"])
        comp_name = form.get(f"comp_{comp_index}_name", "")
        
        if not comp_name:  # Skip empty rows
            comp_index += 1
            continue
            
        if typ == "einfach":
            thema = form.get(f"comp_{comp_index}_thema")
            anmerkungen = form.get(f"comp_{comp_index}_anmerkungen", "")
            competency = {
                "id": comp_id,
                "typ": "einfach",
                "name": comp_name,
                "thema": int(thema) if thema else None,
                "anmerkungen": anmerkungen,
            }
        else:  # niveau
            bp_nummer = form.get(f"comp_{comp_index}_bp_nummer", "")
            moeglichkeiten_str = form.get(f"comp_{comp_index}_moeglichkeiten", "")
            anmerkungen = form.get(f"comp_{comp_index}_anmerkungen", "")
            moeglichkeiten = [m.strip() for m in moeglichkeiten_str.split(";") if m.strip()]
            competency = {
                "id": comp_id,
                "typ": "niveau",
                "name": comp_name,
                "bp_nummer": bp_nummer,
                "moeglichkeiten": moeglichkeiten,
                "anmerkungen": anmerkungen,
            }
        
        competencies.append(competency)
        comp_index += 1
    
    data = {
        "name": name,
        "grade_level": grade_level,
        "typ": typ,
        "competencies": competencies,
    }
    
    # Update in DB (keep existing questions)
    db.save_teacher_list(
        list_id=list_id,
        name=name,
        grade_level=grade_level,
        uploaded_by=user["upn"],
        data=data,
        questions=teacher_list.get("questions", {}),
        typ=typ,
    )
    
    return RedirectResponse("/teacher/competency-lists", status_code=302)


# ---------------------------------------------------------------------------
# Kompetenzanträge — student-initiated competency claims
# ---------------------------------------------------------------------------

@app.post("/antraege/submit")
async def antraege_submit(
    competency_id: str = Form(...),  # Format: e.901, n.989
    typ: str = Form(...),
    beschreibung: str = Form(default=""),
    evidence_url: str = Form(default=""),
    user: dict = Depends(auth.require_user),
):
    if user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Nur für Schüler")
    if typ not in ("einfach", "niveau"):
        raise HTTPException(status_code=400, detail="Ungültiger Typ")

    # competency_id is already in format "e.901" or "n.989"
    comp_id_full = competency_id

    # Must not already be proven
    einfach_map, nachweise_by_comp, _, _ = _load_student_data(user["access_token"], user["oid"])
    if typ == "einfach":
        if einfach_map.get(comp_id_full, {}).get("achieved"):
            raise HTTPException(status_code=400, detail="Bereits nachgewiesen")
        if not beschreibung.strip():
            raise HTTPException(status_code=400, detail="Beschreibung erforderlich")
    else:
        entries = nachweise_by_comp.get(comp_id_full, [])
        if any(e.get("niveau_level", 0) > 0 for e in entries):
            raise HTTPException(status_code=400, detail="Bereits nachgewiesen")
        if not evidence_url.strip():
            raise HTTPException(status_code=400, detail="Link erforderlich")

    # No existing pending antrag for this competency
    for a in db.get_all_kompetenzantraege().values():
        if a["student_id"] == user["oid"] and a["competency_id"] == comp_id_full and a["status"] == "pending":
            raise HTTPException(status_code=400, detail="Antrag bereits gestellt")

    antrag_id = str(uuid.uuid4())
    antrag = {
        "id": antrag_id,
        "student_id": user["oid"],
        "student_name": user["display_name"],
        "competency_id": comp_id_full,  # Store as string (e.901, n.989)
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
    # competency_id is already in format "e.901" or "n.989"
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
async def teacher_coverage(
    request: Request, 
    user: dict = Depends(auth.require_teacher_user),
    class_id: str = "",
):
    # Get available classes
    classes = db.get_classes_with_counts()
    
    # If no class specified, use first one
    if not class_id and classes:
        class_id = classes[0]["id"]
    
    # Get competencies for this class (using separate einfach/niveau lists)
    selected_class = db.get_class(class_id) if class_id else None
    einfach, niveau = _EINFACH, _NIVEAU
    
    if selected_class:
        # Get separate list IDs (fallback to legacy if not set)
        einfach_list_id = selected_class.get("einfach_list_id") or selected_class.get("competency_list_id")
        einfach_list_source = selected_class.get("einfach_list_source") or selected_class.get("list_source", "system")
        niveau_list_id = selected_class.get("niveau_list_id") or selected_class.get("competency_list_id")
        niveau_list_source = selected_class.get("niveau_list_source") or selected_class.get("list_source", "system")
        
        try:
            # Load einfach competencies
            if einfach_list_id:
                comps, _ = _load_competency_list(einfach_list_id, einfach_list_source)
                einfach = [c for c in comps if c["typ"] == "einfach"]
            
            # Load niveau competencies  
            if niveau_list_id:
                comps, _ = _load_competency_list(niveau_list_id, niveau_list_source)
                niveau = [c for c in comps if c["typ"] == "niveau"]
        except FileNotFoundError:
            pass  # Keep fallback values
    
    active_ids = db.get_active_ids(class_id) if class_id is not None else db.get_active_ids()
    
    return templates.TemplateResponse("coverage.html", {
        "request": request, 
        "user": user, 
        "active_ids": active_ids,
        "classes": classes,
        "selected_class_id": class_id,
        "einfach_kompetenzen": einfach,
        "niveau_kompetenzen": niveau,
    })


@app.post("/teacher/coverage/update")
async def teacher_coverage_update(
    request: Request, 
    user: dict = Depends(auth.require_teacher_user),
    class_id: str = Form(""),
):
    form = await request.form()
    ids = {v for k, v in form.multi_items() if k == "active_id"}
    
    if class_id is not None and class_id != "":
        db.set_active_ids(ids, class_id)
    else:
        db.set_active_ids(ids)
    
    return RedirectResponse(url=f"/teacher/coverage?class_id={class_id}", status_code=302)


# ---------------------------------------------------------------------------
# PDF Test Generator  (nur einfache Kompetenzen)
# ---------------------------------------------------------------------------

@app.get("/tests/builder", response_class=HTMLResponse)
async def test_builder(
    request: Request, 
    user: dict = Depends(auth.require_user),
    class_id: str = "",
):
    # Get class-specific competencies (using separate einfach/niveau lists)
    einfach_list = _EINFACH
    niveau_list = _NIVEAU
    active_ids = db.get_active_ids()
    
    if user["is_teacher"]:
        # Teacher: can select class
        groups = db.get_classes_with_counts()
        selected_class_id = class_id
        if not selected_class_id and groups:
            selected_class_id = groups[0]["id"]
        
        if selected_class_id:
            selected_class = db.get_class(selected_class_id)
            if selected_class:
                # Use new separate lists (fallback to legacy if not set)
                einfach_list_id = selected_class.get("einfach_list_id") or selected_class.get("competency_list_id")
                einfach_list_source = selected_class.get("einfach_list_source") or selected_class.get("list_source", "system")
                niveau_list_id = selected_class.get("niveau_list_id") or selected_class.get("competency_list_id")
                niveau_list_source = selected_class.get("niveau_list_source") or selected_class.get("list_source", "system")
                
                try:
                    # Load einfach competencies
                    if einfach_list_id:
                        comps, _ = _load_competency_list(einfach_list_id, einfach_list_source)
                        einfach_list = sorted([c for c in comps if c["typ"] == "einfach"], 
                                             key=lambda k: (k.get("thema") or 999, k["id"]))
                    
                    # Load niveau competencies
                    if niveau_list_id:
                        comps, _ = _load_competency_list(niveau_list_id, niveau_list_source)
                        niveau_list = sorted([c for c in comps if c["typ"] == "niveau"], key=lambda k: k["id"])
                    
                    active_ids = db.get_active_ids(selected_class_id)
                except FileNotFoundError:
                    pass
        
        active_ids_list = json.dumps(sorted(active_ids))
        return templates.TemplateResponse("test_builder.html", {
            "request": request, "user": user,
            "active_ids": active_ids,
            "active_ids_list": active_ids_list,
            "groups": groups,
            "selected_class_id": selected_class_id,
            "einfach_kompetenzen": einfach_list,
            "niveau_kompetenzen": niveau_list,
        })
    
    else:
        # Student: use their class
        student_class = db.get_student_class(user["oid"])
        if student_class:
            # Use new separate lists (fallback to legacy if not set)
            einfach_list_id = student_class.get("einfach_list_id") or student_class.get("competency_list_id")
            einfach_list_source = student_class.get("einfach_list_source") or student_class.get("list_source", "system")
            niveau_list_id = student_class.get("niveau_list_id") or student_class.get("competency_list_id")
            niveau_list_source = student_class.get("niveau_list_source") or student_class.get("list_source", "system")
            
            try:
                # Load einfach competencies
                if einfach_list_id:
                    comps, _ = _load_competency_list(einfach_list_id, einfach_list_source)
                    einfach_list = sorted([c for c in comps if c["typ"] == "einfach"], 
                                         key=lambda k: (k.get("thema") or 999, k["id"]))
                
                # Load niveau competencies
                if niveau_list_id:
                    comps, _ = _load_competency_list(niveau_list_id, niveau_list_source)
                    niveau_list = sorted([c for c in comps if c["typ"] == "niveau"], key=lambda k: k["id"])
                
                active_ids = db.get_active_ids(student_class["id"])
            except FileNotFoundError:
                pass
        
        einfach_map, _, _, _ = _load_student_data(user["access_token"], user["oid"])
        proven_ids = {cid for cid, r in einfach_map.items() if r.get("achieved")}
        reqs = _get_test_requests()
        next_number = sum(1 for r in reqs.values() if r["student_id"] == user["oid"]) + 1
        
        return templates.TemplateResponse("test_builder.html", {
            "request": request, "user": user,
            "proven_ids": proven_ids,
            "active_ids": active_ids,
            "next_number": next_number,
            "einfach_kompetenzen": einfach_list,
            "niveau_kompetenzen": niveau_list,
        })


@app.post("/tests/generate")
async def generate_test(request: Request, user: dict = Depends(auth.require_teacher_user)):
    form = await request.form()
    selected_ids = [v for k, v in form.multi_items() if k == "competency_ids"]

    if not selected_ids:
        raise HTTPException(status_code=400, detail="Keine Kompetenzen ausgewählt")

    student_name = form.get("student_name", "")
    if not student_name:
        raise HTTPException(status_code=400, detail="Kein Schülername angegeben")

    title = form.get("title", "Kompetenztest")
    class_id = form.get("class_id", "")
    pid = _create_preview(student_name, title, selected_ids, class_id=class_id or None)
    return RedirectResponse(f"/tests/preview/{pid}", status_code=303)


@app.post("/tests/request", response_class=HTMLResponse)
async def student_test_request(request: Request, user: dict = Depends(auth.require_user)):
    """Student submits a test request — stored for teacher to review and print."""
    if user["is_teacher"]:
        raise HTTPException(status_code=403, detail="Nur für Schüler")

    form = await request.form()
    selected_ids = [v for k, v in form.multi_items() if k == "competency_ids"]
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
    selected_ids = [v for k, v in form.multi_items() if k == "competency_ids"]

    reqs = _get_test_requests()
    req = reqs.get(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Keine Kompetenzen ausgewählt")

    pid = _create_preview(req["student_name"], req["title"], selected_ids, request_id=req_id)
    return RedirectResponse(f"/tests/preview/{pid}", status_code=303)


@app.post("/tests/delete/{req_id}")
async def delete_test(req_id: str, user: dict = Depends(auth.require_teacher_user)):
    """Teacher deletes a test request (no notification to student)."""
    db.delete_test_request(req_id)
    return RedirectResponse("/tests/pending", status_code=303)


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
async def grade_calculator(
    request: Request, 
    user: dict = Depends(auth.require_user),
    class_id: str = "",
):
    # For teachers: allow class selection
    classes = []
    selected_class_id = class_id
    
    if user["is_teacher"]:
        classes = db.get_classes_with_counts()
        if not selected_class_id and classes:
            selected_class_id = classes[0]["id"]
    else:
        # Students: use their own class
        student_class = db.get_student_class(user["oid"])
        if student_class:
            selected_class_id = student_class["id"]
    
    # Get competencies for selected class
    einfach_list = _EINFACH
    niveau_list = _NIVEAU
    active_ids = db.get_active_ids(selected_class_id) if selected_class_id else db.get_active_ids()
    
    if selected_class_id:
        selected_class = db.get_class(selected_class_id)
        if selected_class and selected_class.get("competency_list_id"):
            try:
                list_source = selected_class.get("list_source", "system")
                comps, _ = _load_competency_list(selected_class["competency_list_id"], list_source)
                einfach_list = sorted([c for c in comps if c["typ"] == "einfach"], 
                                     key=lambda k: (k.get("thema") or 999, k["id"]))
                niveau_list = sorted([c for c in comps if c["typ"] == "niveau"], key=lambda k: (k.get("thema") or 999, k["id"]))
            except FileNotFoundError:
                pass
    
    # Build record map (for students, load their records)
    record_map: dict = {}
    if not user["is_teacher"]:
        einfach_map, nachweise_by_comp, _, _ = _load_student_data(user["access_token"], user["oid"])
        for k in einfach_list:
            r = einfach_map.get(k["id"])
            if r:
                record_map[k["id"]] = r
        for k in niveau_list:
            entries = nachweise_by_comp.get(k["id"], [])
            if entries:
                best = max(entries, key=lambda e: e.get("niveau_level", 0))
                record_map[k["id"]] = {"competency_id": k["id"], "niveau_level": best.get("niveau_level", 0), "achieved": False}
    
    return templates.TemplateResponse("grade_calculator.html", {
        "request": request, "user": user,
        "grade": None, "record_map": record_map,
        "active_ids": active_ids, "basis": "unterricht",
        "classes": classes,
        "selected_class_id": selected_class_id,
        "einfach_kompetenzen": einfach_list,
        "niveau_kompetenzen": niveau_list,
    })


@app.post("/grades/calculate", response_class=HTMLResponse)
async def calculate_grade_form(request: Request, user: dict = Depends(auth.require_user)):
    form = await request.form()
    basis = form.get("basis", "unterricht")
    class_id = form.get("class_id", "")
    
    # Determine class_id for students
    if not user["is_teacher"]:
        student_class = db.get_student_class(user["oid"])
        if student_class:
            class_id = student_class["id"]
    
    # Load class-specific competencies and active_ids
    einfach_list = _EINFACH
    niveau_list = _NIVEAU
    active_ids = db.get_active_ids(class_id) if class_id else db.get_active_ids()
    
    if class_id:
        selected_class = db.get_class(class_id)
        if selected_class and selected_class.get("competency_list_id"):
            try:
                list_source = selected_class.get("list_source", "system")
                comps, _ = _load_competency_list(selected_class["competency_list_id"], list_source)
                einfach_list = [c for c in comps if c["typ"] == "einfach"]
                niveau_list = [c for c in comps if c["typ"] == "niveau"]
            except FileNotFoundError:
                pass
    
    kompetenzen = einfach_list + niveau_list

    records = []
    for k in kompetenzen:
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
        comps = [k for k in kompetenzen if k["id"] in active_ids or k["id"] in proven_ids]
    else:
        comps = kompetenzen

    grade = calculate_grade(records, competencies=comps) if comps else None
    record_map = {r["competency_id"]: r for r in records}
    
    # For teachers: get classes list
    classes = db.get_classes_with_counts() if user["is_teacher"] else []
    
    return templates.TemplateResponse("grade_calculator.html", {
        "request": request, "user": user,
        "grade": grade, "record_map": record_map,
        "active_ids": active_ids, "basis": basis,
        "no_active_warning": basis == "unterricht" and not active_ids,
        "classes": classes,
        "selected_class_id": class_id,
        "einfach_kompetenzen": einfach_list,
        "niveau_kompetenzen": niveau_list,
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
    grade_level: int = Form(...),
    description: str = Form(default=""),
    user: dict = Depends(auth.require_teacher_user),
):
    if name.strip():
        db.add_class(name.strip(), description.strip(), grade_level=grade_level)
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
