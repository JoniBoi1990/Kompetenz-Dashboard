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
            competency_id INTEGER NOT NULL,
            achieved      INTEGER NOT NULL DEFAULT 0,
            updated_by    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (student_id, competency_id)
        );
        CREATE TABLE IF NOT EXISTS nachweise (
            id            TEXT PRIMARY KEY,
            student_id    TEXT NOT NULL,
            student_name  TEXT NOT NULL DEFAULT '',
            competency_id INTEGER NOT NULL,
            niveau_level  INTEGER NOT NULL DEFAULT 0,
            evidence_url  TEXT NOT NULL DEFAULT '',
            evidence_name TEXT NOT NULL DEFAULT '',
            updated_by    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS active_ids (
            competency_id INTEGER PRIMARY KEY
        );
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
            description TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS class_members (
            class_id     TEXT NOT NULL,
            student_id   TEXT NOT NULL,
            student_name TEXT NOT NULL DEFAULT '',
            upn          TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (class_id, student_id)
        );
        """)


# ---------------------------------------------------------------------------
# Active competency IDs (Unterrichtsstand)
# ---------------------------------------------------------------------------

def get_active_ids() -> set[int]:
    with _conn() as con:
        rows = con.execute("SELECT competency_id FROM active_ids").fetchall()
    return {row[0] for row in rows}


def set_active_ids(ids: set[int]) -> None:
    with _conn() as con:
        con.execute("DELETE FROM active_ids")
        con.executemany(
            "INSERT INTO active_ids(competency_id) VALUES(?)",
            [(i,) for i in ids],
        )


# ---------------------------------------------------------------------------
# Einfach records
# ---------------------------------------------------------------------------

def get_einfach_records(student_id: str) -> dict[int, dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM einfach_records WHERE student_id = ?", (student_id,)
        ).fetchall()
    return {row["competency_id"]: dict(row) for row in rows}


def upsert_einfach(
    student_id: str,
    student_name: str,
    competency_id: int,
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

def get_nachweise(student_id: str, competency_id: int | None = None) -> list[dict]:
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
        r["competency_id"] = int(r["competency_id"])
        r["niveau_level"]  = int(r["niveau_level"])
    return result


def add_nachweis(
    student_id: str,
    student_name: str,
    competency_id: int,
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
            """SELECT c.id, c.name, c.description, COUNT(m.student_id) AS member_count
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
            "member_count": r["member_count"],
        }
        for r in rows
    ]


def add_class(name: str, description: str = "", class_id: str | None = None) -> str:
    cid = class_id or str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO classes(id, name, description) VALUES(?, ?, ?)",
            (cid, name.strip(), description.strip()),
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
