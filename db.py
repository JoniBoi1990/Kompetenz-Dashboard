"""
SQLite persistence — replaces Microsoft SharePoint Lists.

All data (competency records, classes, students, requests, …) is stored in
dashboard.db next to this file.  No external services required beyond
Azure AD authentication (User.Read only).
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "dashboard.db"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't exist yet."""
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS einfach_records (
            student_id    TEXT NOT NULL,
            student_name  TEXT NOT NULL DEFAULT '',
            competency_id TEXT NOT NULL,  -- Format: e.901, n.989 (Typ.Prefix+ID)
            achieved      INTEGER NOT NULL DEFAULT 0,
            updated_by    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (student_id, competency_id)
        );
        CREATE TABLE IF NOT EXISTS nachweise (
            id            TEXT PRIMARY KEY,
            student_id    TEXT NOT NULL,
            student_name  TEXT NOT NULL DEFAULT '',
            competency_id TEXT NOT NULL,  -- Format: e.901, n.989 (Typ.Prefix+ID)
            niveau_level  INTEGER NOT NULL DEFAULT 0,
            evidence_url  TEXT NOT NULL DEFAULT '',
            evidence_name TEXT NOT NULL DEFAULT '',
            updated_by    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS active_ids (
            competency_id TEXT NOT NULL,  -- Format: e.901, n.989 (Typ.Prefix+ID)
            class_id TEXT,  -- NULL = global (für Abwärtskompatibilität)
            PRIMARY KEY (competency_id, class_id)
        );
        CREATE INDEX IF NOT EXISTS idx_active_ids_class ON active_ids(class_id);
        CREATE TABLE IF NOT EXISTS test_requests (
            id             TEXT PRIMARY KEY,
            student_id     TEXT NOT NULL,
            student_name   TEXT NOT NULL DEFAULT '',
            title          TEXT NOT NULL DEFAULT '',
            competency_ids TEXT NOT NULL DEFAULT '[]',
            status         TEXT NOT NULL DEFAULT 'pending',
            created_at     TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS kompetenzantraege (
            id   TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS classes (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            grade_level INTEGER,
            competency_list_id TEXT,  -- Legacy: wird durch einfach/niveau ersetzt
            list_source TEXT DEFAULT 'system',  -- Legacy
            einfach_list_id TEXT,
            einfach_list_source TEXT DEFAULT 'system',
            niveau_list_id TEXT,
            niveau_list_source TEXT DEFAULT 'system'
        );
        CREATE TABLE IF NOT EXISTS class_members (
            class_id     TEXT NOT NULL,
            student_id   TEXT NOT NULL,
            student_name TEXT NOT NULL DEFAULT '',
            upn          TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (class_id, student_id)
        );
        CREATE TABLE IF NOT EXISTS teacher_lists (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            grade_level   INTEGER NOT NULL,
            uploaded_by   TEXT NOT NULL,
            uploaded_at   TEXT NOT NULL,
            typ           TEXT NOT NULL DEFAULT 'einfach',  -- 'einfach' oder 'niveau'
            data          TEXT NOT NULL,  -- JSON mit competencies
            questions     TEXT DEFAULT '{}'  -- JSON mit questions
        );
        """)
        
        # Migration: Add questions column if table exists without it
        try:
            con.execute("SELECT questions FROM teacher_lists LIMIT 1")
        except sqlite3.OperationalError:
            con.execute("ALTER TABLE teacher_lists ADD COLUMN questions TEXT DEFAULT '{}' ")
        
        # Migration: Fix active_ids primary key to support composite key (competency_id, class_id)
        try:
            # Check if table exists and has old schema (competency_id as sole PRIMARY KEY)
            rows = con.execute("SELECT name, pk FROM pragma_table_info('active_ids')").fetchall()
            col_map = {name: pk for name, pk in rows}
            # Old schema: competency_id has pk=1, class_id has pk=0 or doesn't exist
            # New schema: competency_id has pk=1, class_id has pk=2 (part of composite PK)
            if col_map.get('competency_id') == 1 and col_map.get('class_id', 1) == 0:
                # Old schema detected: recreate table with composite primary key
                con.execute("ALTER TABLE active_ids RENAME TO active_ids_old")
                con.execute("""
                    CREATE TABLE active_ids (
                        competency_id INTEGER NOT NULL,
                        class_id TEXT,
                        PRIMARY KEY (competency_id, class_id)
                    )
                """)
                con.execute("INSERT OR IGNORE INTO active_ids SELECT * FROM active_ids_old")
                con.execute("DROP TABLE active_ids_old")
        except sqlite3.OperationalError:
            pass  # Table might not exist yet
        
        # Migration: Add typ column to teacher_lists if missing
        try:
            con.execute("SELECT typ FROM teacher_lists LIMIT 1")
        except sqlite3.OperationalError:
            con.execute("ALTER TABLE teacher_lists ADD COLUMN typ TEXT NOT NULL DEFAULT 'einfach'")
        
        # Migration: Add einfach/niveau list columns to classes if missing
        try:
            con.execute("SELECT einfach_list_id FROM classes LIMIT 1")
        except sqlite3.OperationalError:
            con.execute("ALTER TABLE classes ADD COLUMN einfach_list_id TEXT")
            con.execute("ALTER TABLE classes ADD COLUMN einfach_list_source TEXT DEFAULT 'system'")
            con.execute("ALTER TABLE classes ADD COLUMN niveau_list_id TEXT")
            con.execute("ALTER TABLE classes ADD COLUMN niveau_list_source TEXT DEFAULT 'system'")
            
            # Migrate existing data: copy competency_list_id to both einfach and niveau
            con.execute("""
                UPDATE classes SET 
                    einfach_list_id = competency_list_id,
                    einfach_list_source = list_source,
                    niveau_list_id = competency_list_id,
                    niveau_list_source = list_source
                WHERE competency_list_id IS NOT NULL
            """)
        except sqlite3.OperationalError:
            pass  # Table might not exist yet
        
        # Migration: Convert competency_id from INTEGER to TEXT with prefix
        # This requires recreating tables due to SQLite limitations
        _migrate_competency_ids_to_text(con)


def _migrate_competency_ids_to_text(con) -> None:
    """Migrate competency_id columns from INTEGER to TEXT with type prefix.
    Format: e.{id} for einfach, n.{id} for niveau.
    """
    import json
    
    # Helper to convert old numeric ID to new format
    def convert_id(old_id: int, is_niveau: bool = False) -> str:
        prefix = 'n' if is_niveau else 'e'
        return f"{prefix}.{old_id}"
    
    # Helper to determine if ID is niveau based on numeric value
    def is_niveau_id(old_id: int) -> bool:
        # Klasse 9 niveau: 989-1021
        # Klasse 10 niveau: 1071-1103
        if 989 <= old_id <= 1021:
            return True
        if 1071 <= old_id <= 1103:
            return True
        return False
    
    # 1. Migrate active_ids
    try:
        test_row = con.execute("SELECT competency_id FROM active_ids LIMIT 1").fetchone()
        if test_row and isinstance(test_row[0], int):
            con.execute("ALTER TABLE active_ids RENAME TO active_ids_old")
            con.execute("""
                CREATE TABLE active_ids (
                    competency_id TEXT NOT NULL,
                    class_id TEXT,
                    PRIMARY KEY (competency_id, class_id)
                )
            """)
            rows = con.execute("SELECT competency_id, class_id FROM active_ids_old").fetchall()
            for row in rows:
                old_id = row[0]
                class_id = row[1]
                new_id = convert_id(old_id, is_niveau_id(old_id))
                con.execute(
                    "INSERT INTO active_ids (competency_id, class_id) VALUES (?, ?)",
                    (new_id, class_id)
                )
            con.execute("DROP TABLE active_ids_old")
    except Exception:
        pass
    
    # 2. Migrate einfach_records (always einfach type)
    try:
        test_row = con.execute("SELECT competency_id FROM einfach_records LIMIT 1").fetchone()
        if test_row and isinstance(test_row[0], int):
            con.execute("ALTER TABLE einfach_records RENAME TO einfach_records_old")
            con.execute("""
                CREATE TABLE einfach_records (
                    student_id TEXT NOT NULL,
                    student_name TEXT NOT NULL DEFAULT '',
                    competency_id TEXT NOT NULL,
                    achieved INTEGER NOT NULL DEFAULT 0,
                    updated_by TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (student_id, competency_id)
                )
            """)
            rows = con.execute("SELECT * FROM einfach_records_old").fetchall()
            for row in rows:
                old_id = row["competency_id"]
                new_id = convert_id(old_id, False)  # Always einfach
                con.execute(
                    """INSERT INTO einfach_records 
                       (student_id, student_name, competency_id, achieved, updated_by, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (row["student_id"], row["student_name"], new_id, 
                     row["achieved"], row["updated_by"], row["updated_at"])
                )
            con.execute("DROP TABLE einfach_records_old")
    except Exception:
        pass
    
    # 3. Migrate nachweise (always niveau type)
    try:
        test_row = con.execute("SELECT competency_id FROM nachweise LIMIT 1").fetchone()
        if test_row and isinstance(test_row[0], int):
            con.execute("ALTER TABLE nachweise RENAME TO nachweise_old")
            con.execute("""
                CREATE TABLE nachweise (
                    id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    student_name TEXT NOT NULL DEFAULT '',
                    competency_id TEXT NOT NULL,
                    niveau_level INTEGER NOT NULL DEFAULT 0,
                    evidence_url TEXT NOT NULL DEFAULT '',
                    evidence_name TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
            """)
            rows = con.execute("SELECT * FROM nachweise_old").fetchall()
            for row in rows:
                old_id = row["competency_id"]
                new_id = convert_id(old_id, True)  # Always niveau
                con.execute(
                    """INSERT INTO nachweise 
                       (id, student_id, student_name, competency_id, niveau_level,
                        evidence_url, evidence_name, updated_by, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["id"], row["student_id"], row["student_name"], new_id,
                     row["niveau_level"], row["evidence_url"], row["evidence_name"],
                     row["updated_by"], row["updated_at"])
                )
            con.execute("DROP TABLE nachweise_old")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Active competency IDs (Unterrichtsstand)
# ---------------------------------------------------------------------------

def get_active_ids(class_id: str | None = None) -> set[str]:
    """Get active competency IDs. If class_id provided, returns class-specific IDs,
    otherwise returns global active IDs (where class_id IS NULL).
    IDs are now strings with format: e.{number} or n.{number}"""
    with _conn() as con:
        if class_id is not None:
            rows = con.execute(
                "SELECT competency_id FROM active_ids WHERE class_id = ?",
                (class_id,)
            ).fetchall()
        else:
            # For backward compatibility: return IDs with NULL class_id
            rows = con.execute(
                "SELECT competency_id FROM active_ids WHERE class_id IS NULL"
            ).fetchall()
    return {row[0] for row in rows}


def set_active_ids(ids: set[str], class_id: str | None = None) -> None:
    """Set active competency IDs. If class_id provided, sets class-specific IDs.
    IDs are now strings with format: e.{number} or n.{number}"""
    with _conn() as con:
        if class_id is not None:
            con.execute("DELETE FROM active_ids WHERE class_id = ?", (class_id,))
            con.executemany(
                "INSERT INTO active_ids(competency_id, class_id) VALUES(?, ?)",
                [(i, class_id) for i in ids],
            )
        else:
            # Global active IDs (backward compatibility)
            con.execute("DELETE FROM active_ids WHERE class_id IS NULL")
            con.executemany(
                "INSERT INTO active_ids(competency_id, class_id) VALUES(?, NULL)",
                [(i,) for i in ids],
            )


# ---------------------------------------------------------------------------
# Einfach records
# ---------------------------------------------------------------------------

def get_einfach_records(student_id: str) -> dict[str, dict]:
    """Get einfach records for a student. Returns dict with competency_id as key.
    competency_id is now a string (e.901, n.989)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM einfach_records WHERE student_id = ?", (student_id,)
        ).fetchall()
    return {row["competency_id"]: dict(row) for row in rows}


def upsert_einfach(
    student_id: str,
    student_name: str,
    competency_id: str,  # Format: e.901, n.989
    achieved: bool,
    updated_by: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT INTO einfach_records
               (student_id, student_name, competency_id, achieved, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(student_id, competency_id) DO UPDATE SET
                 student_name = excluded.student_name,
                 achieved     = excluded.achieved,
                 updated_by   = excluded.updated_by,
                 updated_at   = excluded.updated_at""",
            (student_id, student_name, competency_id, int(achieved), updated_by, now),
        )


# ---------------------------------------------------------------------------
# Nachweise (niveau evidence)
# ---------------------------------------------------------------------------

def get_nachweise(student_id: str, competency_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if competency_id is not None:
            rows = con.execute(
                "SELECT * FROM nachweise WHERE student_id=? AND competency_id=?"
                " ORDER BY updated_at DESC",
                (student_id, competency_id),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM nachweise WHERE student_id=? ORDER BY updated_at DESC",
                (student_id,),
            ).fetchall()
    result = [dict(row) for row in rows]
    for r in result:
        # competency_id is now a string (e.901, n.989)
        r["niveau_level"] = int(r["niveau_level"])
    return result


def add_nachweis(
    student_id: str,
    student_name: str,
    competency_id: str,  # Format: e.901, n.989
    niveau_level: int,
    evidence_url: str,
    evidence_name: str,
    updated_by: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT INTO nachweise
               (id, student_id, student_name, competency_id, niveau_level,
                evidence_url, evidence_name, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), student_id, student_name, competency_id,
                niveau_level, evidence_url, evidence_name or evidence_url,
                updated_by, now,
            ),
        )


# ---------------------------------------------------------------------------
# Test requests
# ---------------------------------------------------------------------------

def get_test_requests() -> dict[str, dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM test_requests").fetchall()
    result = {}
    for row in rows:
        d = dict(row)
        d["competency_ids"] = json.loads(d["competency_ids"])
        result[d["id"]] = d
    return result


def save_test_request(req: dict) -> None:
    r = dict(req)
    r["competency_ids"] = json.dumps(r.get("competency_ids", []))
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO test_requests
               (id, student_id, student_name, title, competency_ids, status, created_at)
               VALUES (:id, :student_id, :student_name, :title,
                       :competency_ids, :status, :created_at)""",
            r,
        )


def update_test_request_status(req_id: str, status: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE test_requests SET status=? WHERE id=?", (status, req_id)
        )


# ---------------------------------------------------------------------------
# Kompetenzanträge
# ---------------------------------------------------------------------------

def get_all_kompetenzantraege() -> dict[str, dict]:
    with _conn() as con:
        rows = con.execute("SELECT id, data FROM kompetenzantraege").fetchall()
    return {row["id"]: json.loads(row["data"]) for row in rows}


def save_kompetenzantrag(antrag: dict) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO kompetenzantraege(id, data) VALUES(?, ?)",
            (antrag["id"], json.dumps(antrag)),
        )


# ---------------------------------------------------------------------------
# Classes and members
# ---------------------------------------------------------------------------

def get_classes() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM classes ORDER BY name").fetchall()
    return [
        {"id": row["id"], "displayName": row["name"], "description": row["description"]}
        for row in rows
    ]


def get_classes_with_counts() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT c.id, c.name, c.description, c.grade_level, 
                      c.competency_list_id, c.list_source,
                      c.einfach_list_id, c.einfach_list_source,
                      c.niveau_list_id, c.niveau_list_source,
                      COUNT(m.student_id) AS member_count
               FROM classes c
               LEFT JOIN class_members m ON c.id = m.class_id
               GROUP BY c.id
               ORDER BY c.name"""
        ).fetchall()
    return [
        {
            "id": r["id"],
            "displayName": r["name"],
            "description": r["description"],
            "grade_level": r["grade_level"],
            "competency_list_id": r["competency_list_id"],
            "list_source": r["list_source"],
            "einfach_list_id": r["einfach_list_id"],
            "einfach_list_source": r["einfach_list_source"],
            "niveau_list_id": r["niveau_list_id"],
            "niveau_list_source": r["niveau_list_source"],
            "member_count": r["member_count"],
        }
        for r in rows
    ]


def get_class(class_id: str) -> dict | None:
    """Get a single class with all details."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM classes WHERE id = ?",
            (class_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "displayName": row["name"],
        "name": row["name"],
        "description": row["description"],
        "grade_level": row["grade_level"],
        "competency_list_id": row["competency_list_id"],
        "list_source": row["list_source"],
        "einfach_list_id": row["einfach_list_id"],
        "einfach_list_source": row["einfach_list_source"],
        "niveau_list_id": row["niveau_list_id"],
        "niveau_list_source": row["niveau_list_source"],
    }


def get_student_class(student_id: str) -> dict | None:
    """Get the class that a student belongs to."""
    with _conn() as con:
        row = con.execute(
            """SELECT c.* FROM classes c
               JOIN class_members m ON c.id = m.class_id
               WHERE m.student_id = ?""",
            (student_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "displayName": row["name"],
        "name": row["name"],
        "description": row["description"],
        "grade_level": row["grade_level"],
        "competency_list_id": row["competency_list_id"],
        "list_source": row["list_source"],
        "einfach_list_id": row["einfach_list_id"],
        "einfach_list_source": row["einfach_list_source"],
        "niveau_list_id": row["niveau_list_id"],
        "niveau_list_source": row["niveau_list_source"],
    }


def set_class_competency_list(class_id: str, list_id: str, list_source: str = "system") -> None:
    """Set the competency list for a class (legacy - sets both einfach and niveau)."""
    with _conn() as con:
        con.execute(
            """UPDATE classes SET 
                competency_list_id = ?, list_source = ?,
                einfach_list_id = ?, einfach_list_source = ?,
                niveau_list_id = ?, niveau_list_source = ?
               WHERE id = ?""",
            (list_id, list_source, list_id, list_source, list_id, list_source, class_id)
        )


def set_class_competency_lists(
    class_id: str,
    einfach_list_id: str | None = None,
    einfach_list_source: str = "system",
    niveau_list_id: str | None = None,
    niveau_list_source: str = "system",
) -> None:
    """Set separate einfach and niveau competency lists for a class."""
    with _conn() as con:
        con.execute(
            """UPDATE classes SET 
                einfach_list_id = ?, einfach_list_source = ?,
                niveau_list_id = ?, niveau_list_source = ?
               WHERE id = ?""",
            (einfach_list_id, einfach_list_source, niveau_list_id, niveau_list_source, class_id)
        )


def add_class(
    name: str, 
    description: str = "", 
    class_id: str | None = None,
    grade_level: int | None = None,
    competency_list_id: str | None = None,
    list_source: str = "system",
    einfach_list_id: str | None = None,
    einfach_list_source: str = "system",
    niveau_list_id: str | None = None,
    niveau_list_source: str = "system",
) -> str:
    cid = class_id or str(uuid.uuid4())
    # Use competency_list_id as fallback for new fields
    el_id = einfach_list_id or competency_list_id
    nl_id = niveau_list_id or competency_list_id
    el_src = einfach_list_source or list_source
    nl_src = niveau_list_source or list_source
    
    with _conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO classes(id, name, description, grade_level, 
                                             competency_list_id, list_source,
                                             einfach_list_id, einfach_list_source,
                                             niveau_list_id, niveau_list_source) 
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, name.strip(), description.strip(), grade_level, 
             competency_list_id, list_source,
             el_id, el_src, nl_id, nl_src),
        )
    return cid


def update_class(class_id: str, name: str, description: str = "") -> None:
    with _conn() as con:
        con.execute(
            "UPDATE classes SET name=?, description=? WHERE id=?",
            (name.strip(), description.strip(), class_id),
        )


def delete_class(class_id: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM class_members WHERE class_id=?", (class_id,))
        con.execute("DELETE FROM classes WHERE id=?", (class_id,))


def get_class_members(class_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM class_members WHERE class_id=? ORDER BY student_name",
            (class_id,),
        ).fetchall()
    return [
        {
            "id": row["student_id"],
            "displayName": row["student_name"],
            "userPrincipalName": row["upn"],
        }
        for row in rows
    ]


def add_class_member(
    class_id: str, student_id: str, student_name: str, upn: str
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO class_members
               (class_id, student_id, student_name, upn)
               VALUES(?, ?, ?, ?)""",
            (class_id, student_id.strip(), student_name.strip(), upn.strip()),
        )


def delete_class_member(class_id: str, student_id: str) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM class_members WHERE class_id=? AND student_id=?",
            (class_id, student_id),
        )


def import_class_members_csv(class_id: str, rows: list[dict]) -> int:
    """
    Bulk-import members from parsed CSV rows.
    Expected columns: Name (or Vorname + Nachname), UPN (or E-Mail or UserPrincipalName).
    Returns number of rows imported.
    """
    count = 0
    with _conn() as con:
        for row in rows:
            name = (
                row.get("Name")
                or f"{row.get('Vorname', '')} {row.get('Nachname', '')}".strip()
            )
            upn = (
                row.get("UPN")
                or row.get("E-Mail")
                or row.get("UserPrincipalName")
                or ""
            )
            student_id = row.get("student_id") or row.get("ID") or upn or name
            if not name:
                continue
            con.execute(
                """INSERT OR REPLACE INTO class_members
                   (class_id, student_id, student_name, upn)
                   VALUES(?, ?, ?, ?)""",
                (class_id, student_id.strip(), name.strip(), upn.strip()),
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Teacher-uploaded competency lists
# ---------------------------------------------------------------------------

def save_teacher_list(
    list_id: str,
    name: str,
    grade_level: int,
    uploaded_by: str,
    data: dict,
    questions: dict | None = None,
    typ: str = "einfach",
) -> None:
    """Save a teacher-uploaded competency list."""
    import json
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO teacher_lists
               (id, name, grade_level, uploaded_by, uploaded_at, typ, data, questions)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (list_id, name.strip(), grade_level, uploaded_by, now, typ,
             json.dumps(data), json.dumps(questions or {})),
        )


def get_teacher_lists(uploaded_by: str | None = None) -> list[dict]:
    """Get all teacher-uploaded lists, optionally filtered by uploader."""
    import json
    with _conn() as con:
        if uploaded_by:
            rows = con.execute(
                "SELECT * FROM teacher_lists WHERE uploaded_by = ? ORDER BY name",
                (uploaded_by,)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM teacher_lists ORDER BY name"
            ).fetchall()
    
    result = []
    for row in rows:
        data = json.loads(row["data"])
        questions = json.loads(row["questions"] if row["questions"] else '{}')
        result.append({
            "id": row["id"],
            "name": row["name"],
            "grade_level": row["grade_level"],
            "uploaded_by": row["uploaded_by"],
            "uploaded_at": row["uploaded_at"],
            "typ": row["typ"],
            "competency_count": len(data.get("competencies", [])),
            "question_count": sum(len(v) for v in questions.values()),
            "data": data,
            "questions": questions,
        })
    return result


def get_teacher_list(list_id: str) -> dict | None:
    """Get a specific teacher-uploaded list."""
    import json
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM teacher_lists WHERE id = ?",
            (list_id,)
        ).fetchone()
    
    if not row:
        return None
    
    data = json.loads(row["data"])
    questions = json.loads(row["questions"] if row["questions"] else '{}')
    return {
        "id": row["id"],
        "name": row["name"],
        "grade_level": row["grade_level"],
        "uploaded_by": row["uploaded_by"],
        "uploaded_at": row["uploaded_at"],
        "typ": row["typ"],
        "competency_count": len(data.get("competencies", [])),
        "question_count": sum(len(v) for v in questions.values()),
        "data": data,
        "questions": questions,
    }


def delete_teacher_list(list_id: str, uploaded_by: str) -> bool:
    """Delete a teacher-uploaded list. Only the uploader can delete."""
    with _conn() as con:
        cursor = con.execute(
            "DELETE FROM teacher_lists WHERE id = ? AND uploaded_by = ?",
            (list_id, uploaded_by)
        )
        return cursor.rowcount > 0
