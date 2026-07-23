# Klassen-Archivierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Klassen zum Schuljahresende als JSON-Archiv herunterladen und danach vollständig (DB + Backup-Dateien) vom Server löschen — ohne verbleibende Personendaten.

**Architecture:** Zuerst Schema-Migration (`class_id`-Spalte in den vier Schülerdaten-Tabellen, Backfill über `class_members`, Neuaufbau von `einfach_records` mit neuem PK). Darauf aufbauend ein zweistufiger Archiv-Flow im bestehenden Admin-Backup-Bereich (erstellen → Download erzwingen → mit getipptem Klassennamen löschen) plus Waisen-Bereinigung für NULL-`class_id`-Zeilen.

**Tech Stack:** FastAPI, SQLite (via `db.py`), Jinja2-Templates, ReportLab (unberührt), kein Test-Framework — Verifikation per `.venv/bin/python`-Snippets und Browser-Checkliste.

**Spec:** `docs/superpowers/specs/2026-07-23-klassen-archivierung-design.md`

## Global Constraints

- Branch: **`agent-dev`**, niemals auf `main` committen. Commit-Format: `agent: <kurze Beschreibung>`.
- Kompetenz-IDs sind **Strings** (`e.901`, `n.989`) — niemals `int()`/`parseInt()`.
- UI-Texte auf Deutsch, Code-Kommentare deutsch für fachliche Logik.
- Kein pytest einführen — Verifikation wie in den Tasks angegeben (Projektkonvention: manuelles Testing).
- Keine Änderungen an `.env`/DEV_MODE committen.
- `delete_onenote_sync_config()` **nicht** in der Lösch-Kaskade aufrufen (öffnet eigene Connection = eigene Transaktion) — stattdessen Inline-DELETEs in der Kaskaden-Transaktion.
- Bekannte SQLite-Eigenheit: `ON CONFLICT` mit `class_id = NULL` greift nicht (NULLs gelten als verschieden). Betrifft nur Waisen-Schüler ohne Klasse; dokumentiert, kein Fix nötig.

---

### Task 1: `.gitignore` härten (Datenschutz)

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nichts
- Produces: `_backup/`, `backup_onenote_*.json`, `dashboard.db.backup.*` werden von git ignoriert

- [ ] **Step 1: `.gitignore` erweitern**

Im Abschnitt `# Uploads / generated data (not source-controlled)` nach der Zeile `dashboard.db` ergänzen:

```gitignore
dashboard.db.backup.*
_backup/
backup_onenote_*.json
```

- [ ] **Step 2: Verifizieren**

Run:
```bash
git check-ignore -v _backup/manual dashboard.db.backup.20260319_230528 backup_onenote_2026-03-28_195547.json
```
Expected: drei Zeilen mit jeweils einem `.gitignore`-Match (Exit-Code 0).

Run:
```bash
git status --short
```
Expected: Keine `_backup/`- oder `backup_onenote_*`-Dateien als untracked gelistet.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "agent: gitignore haertet gegen Personendaten (Backups, DB-Kopien)"
```

---

### Task 2: Schema-Migration `class_id` (db.py)

**Files:**
- Modify: `db.py` (in `init_db()` nach Zeile 169, davor neue Funktion `_migrate_add_class_ids`)

**Interfaces:**
- Consumes: bestehende Tabellen `class_members`, `einfach_records`, `nachweise`, `test_requests`, `kompetenzantraege`
- Produces: `_migrate_add_class_ids(con) -> None`; `_count_orphaned(con) -> dict`; `count_orphaned_records() -> dict`; `delete_orphaned_records() -> dict` (Task 6 und 7 nutzen die beiden letzten)

- [ ] **Step 1: Migrations- und Waisen-Funktionen schreiben**

In `db.py` direkt vor `def init_db()` einfügen:

```python
def _count_orphaned(con) -> dict:
    """Zählt Datensätze ohne Klassenzuordnung (Waisen)."""
    return {
        "einfach_records": con.execute(
            "SELECT COUNT(*) AS c FROM einfach_records WHERE class_id IS NULL"
        ).fetchone()["c"],
        "nachweise": con.execute(
            "SELECT COUNT(*) AS c FROM nachweise WHERE class_id IS NULL"
        ).fetchone()["c"],
        "test_requests": con.execute(
            "SELECT COUNT(*) AS c FROM test_requests WHERE class_id IS NULL"
        ).fetchone()["c"],
        "kompetenzantraege": con.execute(
            "SELECT COUNT(*) AS c FROM kompetenzantraege WHERE class_id IS NULL"
        ).fetchone()["c"],
        "test_counters": con.execute(
            "SELECT COUNT(*) AS c FROM test_counters "
            "WHERE student_id NOT IN (SELECT student_id FROM class_members)"
        ).fetchone()["c"],
    }


def count_orphaned_records() -> dict:
    """Öffentliche Variante von _count_orphaned mit eigener Connection."""
    with _conn() as con:
        return _count_orphaned(con)


def delete_orphaned_records() -> dict:
    """Löscht alle Waisen-Datensätze. Gibt die Anzahlen vor der Löschung zurück."""
    with _conn() as con:
        counts = _count_orphaned(con)
        con.execute("DELETE FROM einfach_records WHERE class_id IS NULL")
        con.execute("DELETE FROM nachweise WHERE class_id IS NULL")
        con.execute("DELETE FROM test_requests WHERE class_id IS NULL")
        con.execute("DELETE FROM kompetenzantraege WHERE class_id IS NULL")
        con.execute(
            "DELETE FROM test_counters "
            "WHERE student_id NOT IN (SELECT student_id FROM class_members)"
        )
        return counts


def _migrate_add_class_ids(con) -> None:
    """Fügt class_id-Spalten zu den Schülerdaten-Tabellen hinzu und befüllt sie
    aus class_members. Waisen (keine Mitgliedschaft ableitbar) bleiben NULL und
    werden im Server-Log gemeldet."""
    # einfach_records: Neuaufbau mit PK (student_id, class_id, competency_id)
    cols = [
        r["name"]
        for r in con.execute("SELECT name FROM pragma_table_info('einfach_records')").fetchall()
    ]
    if "class_id" not in cols:
        con.execute("ALTER TABLE einfach_records RENAME TO einfach_records_old")
        con.execute("""
            CREATE TABLE einfach_records (
                student_id    TEXT NOT NULL,
                class_id      TEXT,
                student_name  TEXT NOT NULL DEFAULT '',
                competency_id TEXT NOT NULL,
                achieved      INTEGER NOT NULL DEFAULT 0,
                updated_by    TEXT NOT NULL DEFAULT '',
                updated_at    TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (student_id, class_id, competency_id)
            )
        """)
        con.execute("""
            INSERT OR IGNORE INTO einfach_records
                (student_id, class_id, student_name, competency_id, achieved,
                 updated_by, updated_at)
            SELECT r.student_id,
                   (SELECT m.class_id FROM class_members m
                    WHERE m.student_id = r.student_id LIMIT 1),
                   r.student_name, r.competency_id, r.achieved,
                   r.updated_by, r.updated_at
            FROM einfach_records_old r
        """)
        con.execute("DROP TABLE einfach_records_old")

    # Übrige Tabellen: einfache Spalten-Erweiterung
    for table in ("nachweise", "test_requests", "kompetenzantraege"):
        cols = [
            r["name"]
            for r in con.execute(f"SELECT name FROM pragma_table_info('{table}')").fetchall()
        ]
        if "class_id" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN class_id TEXT")

    # Backfill aus class_members (aktuell: jeder Schüler in genau einer Klasse)
    con.execute("""
        UPDATE nachweise SET class_id =
            (SELECT m.class_id FROM class_members m
             WHERE m.student_id = nachweise.student_id LIMIT 1)
        WHERE class_id IS NULL
    """)
    con.execute("""
        UPDATE test_requests SET class_id =
            (SELECT m.class_id FROM class_members m
             WHERE m.student_id = test_requests.student_id LIMIT 1)
        WHERE class_id IS NULL
    """)
    con.execute("""
        UPDATE kompetenzantraege SET class_id =
            (SELECT m.class_id FROM class_members m
             WHERE m.student_id = json_extract(kompetenzantraege.data, '$.student_id')
             LIMIT 1)
        WHERE class_id IS NULL
    """)

    # Waisen melden (Bereinigung erfolgt über Admin-UI, siehe Task 6/7)
    orphans = _count_orphaned(con)
    total = sum(orphans.values())
    if total:
        print(
            f"WARNING migration class_id: {total} verwaiste Datensaetze ohne "
            f"Klassenzuordnung: {orphans}"
        )
```

- [ ] **Step 2: Migration in `init_db()` einhängen**

In `init_db()` direkt nach der Zeile `_migrate_competency_ids_to_text(con)` (db.py:169) ergänzen:

```python
        # Migration: class_id-Spalten für Schülerdaten-Tabellen
        _migrate_add_class_ids(con)
```

- [ ] **Step 3: Auf Kopie der echten DB verifizieren**

Run:
```bash
cp dashboard.db /tmp/migration-test.db
.venv/bin/python - <<'EOF'
from pathlib import Path
import sqlite3
import db

db.DB_PATH = Path("/tmp/migration-test.db")
db.init_db()

con = sqlite3.connect("/tmp/migration-test.db")
con.row_factory = sqlite3.Row
for t in ("einfach_records", "nachweise", "test_requests", "kompetenzantraege"):
    cols = [r["name"] for r in con.execute(f"SELECT name FROM pragma_table_info('{t}')")]
    assert "class_id" in cols, f"{t}: class_id fehlt!"
    total = con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
    nulls = con.execute(f"SELECT COUNT(*) c FROM {t} WHERE class_id IS NULL").fetchone()["c"]
    print(f"{t}: {total} Zeilen, {nulls} ohne class_id")

pk = [r["name"] for r in con.execute(
    "SELECT name FROM pragma_table_info('einfach_records') WHERE pk > 0 ORDER BY pk")]
assert pk == ["student_id", "class_id", "competency_id"], f"PK falsch: {pk}"
print("PK einfach_records OK:", pk)

# Idempotenz: zweites init_db() darf nichts kaputt machen
db.init_db()
print("Zweiter init_db()-Lauf OK (idempotent)")
EOF
```
Expected: alle vier Tabellen haben `class_id`, PK ist `(student_id, class_id, competency_id)`, Counts werden ausgegeben, kein AssertionError, zweiter Lauf fehlerfrei. Etwaige `WARNING ... verwaiste Datensaetze` ist erwartetes Verhalten (echte Alt-Daten).

Danach Scratch-DB löschen: `rm /tmp/migration-test.db`

- [ ] **Step 4: Commit**

```bash
git add db.py
git commit -m "agent: Migration class_id fuer Schuelerdaten-Tabellen + Waisen-Funktionen"
```

---

### Task 3: Schreibpfade setzen `class_id`

**Files:**
- Modify: `db.py` (`_class_id_for_student` neu; `upsert_einfach` :343, `add_nachweis` :389, `save_test_request` :458, `save_kompetenzantrag` :534, `bulk_upsert_einfach` :995, `bulk_add_nachweise` :1037, `migrate_student` :750)
- Modify: `backup.py` (`restore_backup` :298 — zwei Aufrufstellen)
- Modify: `onenote_sync.py` (:429 und :456 — je ein kwarg)

**Interfaces:**
- Consumes: Task-2-Schema (Spalte `class_id` existiert in allen vier Tabellen)
- Produces: `_class_id_for_student(con, student_id) -> str | None`; `upsert_einfach(..., class_id: str | None = None)`; `add_nachweis(..., class_id: str | None = None)`; `bulk_*` akzeptieren optionalen `class_id`-Key pro Record. Task 4 und 6 setzen voraus, dass neue Writes immer `class_id` tragen.

- [ ] **Step 1: Hilfsfunktion in `db.py`**

Direkt vor `upsert_einfach` einfügen:

```python
def _class_id_for_student(con, student_id: str) -> str | None:
    """Leitet die class_id eines Schülers aus class_members ab (None = Waise)."""
    row = con.execute(
        "SELECT class_id FROM class_members WHERE student_id = ? LIMIT 1",
        (student_id,),
    ).fetchone()
    return row["class_id"] if row else None
```

- [ ] **Step 2: `upsert_einfach` anpassen**

Kompletter Ersatz der Funktion:

```python
def upsert_einfach(
    student_id: str,
    student_name: str,
    competency_id: str,  # Format: e.901, n.989
    achieved: bool,
    updated_by: str,
    class_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        if class_id is None:
            class_id = _class_id_for_student(con, student_id)
        con.execute(
            """INSERT INTO einfach_records
               (student_id, class_id, student_name, competency_id, achieved, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(student_id, class_id, competency_id) DO UPDATE SET
                 student_name = excluded.student_name,
                 achieved     = excluded.achieved,
                 updated_by   = excluded.updated_by,
                 updated_at   = excluded.updated_at""",
            (student_id, class_id, student_name, competency_id, int(achieved), updated_by, now),
        )
```

- [ ] **Step 3: `add_nachweis` anpassen**

Signatur um `class_id: str | None = None` erweitern; Body:

```python
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        if class_id is None:
            class_id = _class_id_for_student(con, student_id)
        con.execute(
            """INSERT INTO nachweise
               (id, student_id, class_id, student_name, competency_id, niveau_level,
                evidence_url, evidence_name, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), student_id, class_id, student_name, competency_id,
                niveau_level, evidence_url, evidence_name or evidence_url,
                updated_by, now,
            ),
        )
```

- [ ] **Step 4: `save_test_request` anpassen**

```python
def save_test_request(req: dict) -> None:
    r = dict(req)
    r["competency_ids"] = json.dumps(r.get("competency_ids", []))
    with _conn() as con:
        r["class_id"] = r.get("class_id") or _class_id_for_student(con, r["student_id"])
        con.execute(
            """INSERT OR REPLACE INTO test_requests
               (id, student_id, class_id, student_name, title, competency_ids, status, created_at)
               VALUES (:id, :student_id, :class_id, :student_name, :title,
                       :competency_ids, :status, :created_at)""",
            r,
        )
```

- [ ] **Step 5: `save_kompetenzantrag` anpassen**

```python
def save_kompetenzantrag(antrag: dict) -> None:
    with _conn() as con:
        class_id = antrag.get("class_id") or _class_id_for_student(
            con, antrag.get("student_id", "")
        )
        con.execute(
            "INSERT OR REPLACE INTO kompetenzantraege(id, class_id, data) VALUES(?, ?, ?)",
            (antrag["id"], class_id, json.dumps(antrag)),
        )
```

- [ ] **Step 6: `bulk_upsert_einfach` und `bulk_add_nachweise` anpassen**

In `bulk_upsert_einfach` pro Record vor dem INSERT:

```python
            cid = record.get("class_id") or _class_id_for_student(con, record["student_id"])
```

INSERT ändern zu (Spalte `class_id` nach `student_id`, Platzhalter `cid` als zweiter Wert, `ON CONFLICT(student_id, class_id, competency_id)`):

```python
            con.execute(
                """INSERT INTO einfach_records
                   (student_id, class_id, student_name, competency_id, achieved, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(student_id, class_id, competency_id) DO UPDATE SET
                     student_name = excluded.student_name,
                     achieved     = excluded.achieved,
                     updated_by   = excluded.updated_by,
                     updated_at   = excluded.updated_at""",
                (
                    record["student_id"],
                    cid,
                    record.get("student_name", ""),
                    record["competency_id"],
                    int(record.get("achieved", False)),
                    record.get("updated_by", ""),
                    record.get("updated_at", now),
                ),
            )
```

In `bulk_add_nachweise` analog — pro Nachweis:

```python
            cid = nw.get("class_id") or _class_id_for_student(con, nw["student_id"])
```

INSERT ändern zu:

```python
            con.execute(
                """INSERT INTO nachweise
                   (id, student_id, class_id, student_name, competency_id, niveau_level,
                    evidence_url, evidence_name, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    nw["student_id"],
                    cid,
                    nw.get("student_name", ""),
                    nw["competency_id"],
                    nw.get("niveau_level", 0),
                    nw.get("evidence_url", ""),
                    nw.get("evidence_name", ""),
                    nw.get("updated_by", ""),
                    nw.get("updated_at", now),
                ),
            )
```

- [ ] **Step 7: `migrate_student` — explizite class_id**

In `migrate_student` (db.py:750) die beiden Aufrufe `upsert_einfach(...)` und `add_nachweis(...)` jeweils um das Argument `class_id=class_id` ergänzen (die Funktion hat `class_id` als Parameter im Scope).

- [ ] **Step 8: `backup.restore_backup` — explizite class_id**

In `backup.py` `restore_backup`: dem `db.upsert_einfach(...)`-Aufruf (:350) und beiden `db.add_nachweis(...)`-Aufrufen (:379, :391) jeweils `class_id=class_id` als kwarg anhängen (`class_id` ist Funktionsparameter).

- [ ] **Step 9: `onenote_sync.py` — explizite class_id**

An den Aufrufstellen `db.upsert_einfach(` (:429) und `db.add_nachweis(` (:456) jeweils `class_id=class_id` als kwarg anhängen (die Sync-Methode hat `class_id` im Scope, vgl. :541).

- [ ] **Step 10: Verifizieren**

Run:
```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
import db

db.DB_PATH = Path("/tmp/write-test.db")
Path("/tmp/write-test.db").unlink(missing_ok=True)
db.init_db()

db.add_class("Testklasse", "", grade_level=9)
cid = db.get_classes()[0]["id"]
db.add_class_member(cid, "s1@schule.de", "Schüler Eins", "s1@schule.de")

# Alle Schreibpfade
db.upsert_einfach("s1@schule.de", "Schüler Eins", "e.901", True, "test")
db.add_nachweis("s1@schule.de", "Schüler Eins", "n.989", 2, "http://x", "Beleg", "test")
db.save_test_request({"id": "r1", "student_id": "s1@schule.de", "student_name": "Schüler Eins",
                      "title": "T", "competency_ids": ["e.901"], "status": "pending",
                      "created_at": "2026-07-23"})
db.save_kompetenzantrag({"id": "a1", "student_id": "s1@schule.de", "student_name": "Schüler Eins"})
db.bulk_upsert_einfach([{"student_id": "s1@schule.de", "student_name": "Schüler Eins",
                         "competency_id": "e.902", "achieved": True, "updated_by": "test"}])
db.bulk_add_nachweise([{"student_id": "s1@schule.de", "student_name": "Schüler Eins",
                        "competency_id": "n.990", "niveau_level": 1,
                        "evidence_url": "http://y", "evidence_name": "B2", "updated_by": "test"}])

import sqlite3
con = sqlite3.connect("/tmp/write-test.db")
for table, expect in [("einfach_records", 2), ("nachweise", 2), ("test_requests", 1),
                      ("kompetenzantraege", 1)]:
    rows = con.execute(f"SELECT class_id FROM {table}").fetchall()
    assert len(rows) == expect, f"{table}: {len(rows)} Zeilen statt {expect}"
    assert all(r[0] == cid for r in rows), f"{table}: class_id falsch: {rows}"
    print(f"{table}: OK ({expect} Zeilen mit class_id)")

# Explizite class_id (Restore/Sync-Pfad) überschreibt Ableitung
db.upsert_einfach("s1@schule.de", "Schüler Eins", "e.903", True, "test", class_id="explizit")
row = con.execute("SELECT class_id FROM einfach_records WHERE competency_id='e.903'").fetchone()
assert row[0] == "explizit", row
print("Explizite class_id: OK")
EOF
```
Expected: alle Checks `OK`, kein AssertionError. Danach: `rm /tmp/write-test.db`

- [ ] **Step 11: Commit**

```bash
git add db.py backup.py onenote_sync.py
git commit -m "agent: Schreibpfade setzen class_id (Ableitung via class_members)"
```

---

### Task 4: Lösch-Kaskade `delete_class_cascade` (db.py)

**Files:**
- Modify: `db.py` (nach `delete_class` :708 neue Funktion)

**Interfaces:**
- Consumes: Task-2-Schema; Tabellen `onenote_sync_config`, `onenote_sync_history` (existieren via `init_onenote_sync_tables`)
- Produces: `delete_class_cascade(class_id: str) -> dict` — Stats mit Keys `einfach_records`, `nachweise`, `test_requests`, `kompetenzantraege`, `active_ids`, `onenote`, `members`, `test_counters`. Task 6 ruft diese Funktion auf.

- [ ] **Step 1: Funktion schreiben**

In `db.py` direkt nach `delete_class` einfügen:

```python
def delete_class_cascade(class_id: str) -> dict:
    """
    Löscht eine Klasse vollständig in EINER Transaktion (Datenschutz-Löschung):
    alle Schülerdaten der Klasse, active_ids, OneNote-Config/History,
    Mitgliedschaften und die Klasse selbst. test_counters nur für Schüler,
    die danach in keiner Klasse mehr sind.

    Returns:
        Statistik-Dict mit Anzahlen der gelöschten Zeilen
    """
    stats = {}
    with _conn() as con:
        members = [
            r["student_id"]
            for r in con.execute(
                "SELECT student_id FROM class_members WHERE class_id=?", (class_id,)
            ).fetchall()
        ]
        stats["einfach_records"] = con.execute(
            "DELETE FROM einfach_records WHERE class_id=?", (class_id,)
        ).rowcount
        stats["nachweise"] = con.execute(
            "DELETE FROM nachweise WHERE class_id=?", (class_id,)
        ).rowcount
        stats["test_requests"] = con.execute(
            "DELETE FROM test_requests WHERE class_id=?", (class_id,)
        ).rowcount
        stats["kompetenzantraege"] = con.execute(
            "DELETE FROM kompetenzantraege WHERE class_id=?", (class_id,)
        ).rowcount
        stats["active_ids"] = con.execute(
            "DELETE FROM active_ids WHERE class_id=?", (class_id,)
        ).rowcount
        stats["onenote"] = con.execute(
            "DELETE FROM onenote_sync_history WHERE class_id=?", (class_id,)
        ).rowcount
        stats["onenote"] += con.execute(
            "DELETE FROM onenote_sync_config WHERE class_id=?", (class_id,)
        ).rowcount
        con.execute("DELETE FROM class_members WHERE class_id=?", (class_id,))
        stats["members"] = len(members)
        # test_counters nur entfernen, wenn keine weitere Mitgliedschaft besteht
        counters_deleted = 0
        for sid in members:
            still_member = con.execute(
                "SELECT 1 FROM class_members WHERE student_id=? LIMIT 1", (sid,)
            ).fetchone()
            if not still_member:
                counters_deleted += con.execute(
                    "DELETE FROM test_counters WHERE student_id=?", (sid,)
                ).rowcount
        stats["test_counters"] = counters_deleted
        con.execute("DELETE FROM classes WHERE id=?", (class_id,))
    return stats
```

Hinweis: `_conn()` committed erst am Ende des `with`-Blocks; eine Exception dazwischen verwirft alles (All-or-Nothing).

- [ ] **Step 2: Verifizieren**

Run:
```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
import db

db.DB_PATH = Path("/tmp/cascade-test.db")
Path("/tmp/cascade-test.db").unlink(missing_ok=True)
db.init_db()

# Zwei Klassen, ein Schüler in beiden (Mehrfachmitgliedschaft)
db.add_class("Klasse A", "", grade_level=9)
db.add_class("Klasse B", "", grade_level=10)
a = db.get_classes()[0]["id"]
b = db.get_classes()[1]["id"]
db.add_class_member(a, "s1@schule.de", "Schüler Eins", "s1@schule.de")
db.add_class_member(a, "s2@schule.de", "Schüler Zwei", "s2@schule.de")
db.add_class_member(b, "s1@schule.de", "Schüler Eins", "s1@schule.de")

# Daten in beiden Klassen
db.upsert_einfach("s1@schule.de", "Schüler Eins", "e.901", True, "t", class_id=a)
db.upsert_einfach("s1@schule.de", "Schüler Eins", "e.1001", True, "t", class_id=b)
db.add_nachweis("s2@schule.de", "Schüler Zwei", "n.989", 2, "http://x", "B", "t", class_id=a)
db.save_test_request({"id": "r1", "student_id": "s2@schule.de", "student_name": "Zwei",
                      "title": "T", "competency_ids": [], "status": "pending",
                      "created_at": "x", "class_id": a})
db.get_next_test_number("s2@schule.de")  # counter für s2
db.get_next_test_number("s1@schule.de")  # counter für s1 (bleibt: noch in Klasse B)
db.set_active_ids({"e.901"}, class_id=a)

stats = db.delete_class_cascade(a)
print("Stats:", stats)
assert stats["members"] == 2
assert stats["einfach_records"] == 1 and stats["nachweise"] == 1
assert stats["test_requests"] == 1 and stats["active_ids"] == 1
assert stats["test_counters"] == 1  # nur s2, s1 ist noch in Klasse B

import sqlite3
con = sqlite3.connect("/tmp/cascade-test.db")
# Klasse A ist komplett weg
assert con.execute("SELECT COUNT(*) FROM classes WHERE id=?", (a,)).fetchone()[0] == 0
assert con.execute("SELECT COUNT(*) FROM class_members WHERE class_id=?", (a,)).fetchone()[0] == 0
# Klasse B unberührt: s1-Record mit class_id=b existiert noch
assert con.execute("SELECT COUNT(*) FROM einfach_records WHERE class_id=?", (b,)).fetchone()[0] == 1
assert con.execute("SELECT COUNT(*) FROM test_counters WHERE student_id='s1@schule.de'").fetchone()[0] == 1
assert con.execute("SELECT COUNT(*) FROM test_counters WHERE student_id='s2@schule.de'").fetchone()[0] == 0
print("Kaskade OK: Klasse A gelöscht, Klasse B intakt, Counter korrekt")
EOF
```
Expected: `Kaskade OK: ...`, kein AssertionError. Danach: `rm /tmp/cascade-test.db`

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "agent: delete_class_cascade loescht Klasse transaktional vollstaendig"
```

---

### Task 5: Backup-Verzeichnisse löschen (backup.py)

**Files:**
- Modify: `backup.py` (Import `shutil` oben; neue Funktion nach `delete_backup` :469)

**Interfaces:**
- Consumes: `AUTO_BACKUP_DIR`, `MANUAL_BACKUP_DIR` (backup.py:21-22)
- Produces: `delete_class_backup_dirs(class_id: str) -> list[str]` — Liste der Pfade, die NICHT gelöscht werden konnten (leer = Erfolg). Task 6 ruft sie auf.

- [ ] **Step 1: Import ergänzen**

Oben in `backup.py` bei den Imports (`import json` etc.) ergänzen:

```python
import shutil
```

- [ ] **Step 2: Funktion schreiben**

Nach `delete_backup` einfügen:

```python
def delete_class_backup_dirs(class_id: str) -> list[str]:
    """
    Löscht alle Backup-Verzeichnisse einer Klasse (auto + manual) rekursiv,
    inklusive aller enthaltenen Backup-Dateien.

    Returns:
        Liste der Pfade, die nicht gelöscht werden konnten (leer = alles weg)
    """
    failed: list[str] = []
    for base in (AUTO_BACKUP_DIR, MANUAL_BACKUP_DIR):
        class_dir = (base / class_id).resolve()
        # Sicherheitsprüfung: muss innerhalb des Basis-Verzeichnisses liegen
        if not str(class_dir).startswith(str(base.resolve())):
            failed.append(str(class_dir))
            continue
        if class_dir.exists():
            try:
                shutil.rmtree(class_dir)
            except Exception:
                failed.append(str(class_dir))
    return failed
```

- [ ] **Step 3: Verifizieren**

Run:
```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
import backup

# Test-Verzeichnisse anlegen
for base in (backup.AUTO_BACKUP_DIR, backup.MANUAL_BACKUP_DIR):
    d = base / "testklasse-xyz"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-23_120000.json").write_text("{}", encoding="utf-8")

failed = backup.delete_class_backup_dirs("testklasse-xyz")
assert failed == [], f"Fehlgeschlagen: {failed}"
assert not (backup.AUTO_BACKUP_DIR / "testklasse-xyz").exists()
assert not (backup.MANUAL_BACKUP_DIR / "testklasse-xyz").exists()

# Pfad-Traversal wird blockiert
failed = backup.delete_class_backup_dirs("../../etc")
assert failed != [], "Traversal nicht blockiert!"
print("delete_class_backup_dirs OK (Löschen + Traversal-Schutz)")
EOF
```
Expected: `delete_class_backup_dirs OK (Löschen + Traversal-Schutz)`.

- [ ] **Step 4: Commit**

```bash
git add backup.py
git commit -m "agent: delete_class_backup_dirs entfernt Backup-Dateien einer Klasse"
```

---

### Task 6: Archiv- und Waisen-Routen (main.py)

**Files:**
- Modify: `main.py` (`_PENDING_ARCHIVES` bei :256; `admin_classes` :3017; `admin_class_backups` :3204; neue Routen nach `export_backup_endpoint` ~:3345)

**Interfaces:**
- Consumes: `db.delete_class_cascade` (Task 4), `backup.delete_class_backup_dirs` (Task 5), `db.count_orphaned_records` / `db.delete_orphaned_records` (Task 2), `backup.create_manual_backup`
- Produces: `_PENDING_ARCHIVES: dict[class_id, {"path": str, "downloaded": bool}]`; Routen `POST /admin/classes/{class_id}/archive`, `GET /admin/classes/{class_id}/archive/download`, `POST /admin/classes/{class_id}/archive/delete`, `POST /admin/classes/orphans/delete`; Template-Kontext `archive_pending` (Task 7) und `orphans`/`orphans_total` (Task 7)

- [ ] **Step 1: Pending-State anlegen**

Bei `main.py:256` (`_TEST_PREVIEWS: dict = {}`) direkt darunter ergänzen:

```python
# Ausstehende Klassen-Archive (flüchtig, In-Memory): class_id -> {"path", "downloaded"}
_PENDING_ARCHIVES: dict = {}
```

- [ ] **Step 2: `admin_classes` um Waisen-Daten erweitern**

Bestehende Funktion ersetzen durch:

```python
@app.get("/admin/classes", response_class=HTMLResponse)
async def admin_classes(request: Request, user: dict = Depends(auth.require_teacher_user)):
    classes = db.get_classes_with_counts()
    orphans = db.count_orphaned_records()
    return templates.TemplateResponse("admin_classes.html", {
        "request": request, "user": user, "classes": classes,
        "orphans": orphans, "orphans_total": sum(orphans.values()),
        "msg": request.query_params.get("msg", ""),
    })
```

- [ ] **Step 3: `admin_class_backups` um Archiv-Status erweitern**

Im `TemplateResponse` der Funktion `admin_class_backups` (:3216) den Kontext um einen Key ergänzen:

```python
        "archive_pending": _PENDING_ARCHIVES.get(class_id),
```

- [ ] **Step 4: Archiv-Routen hinzufügen**

Direkt nach `export_backup_endpoint` (~main.py:3345) einfügen:

```python
@app.post("/admin/classes/{class_id}/archive")
async def archive_class_create(
    class_id: str,
    user: dict = Depends(auth.require_teacher_user),
):
    """Schritt 1: Finales Archiv (Backup-Format) für die Klasse erstellen."""
    cls = db.get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Klasse nicht gefunden")
    filepath = backup.create_manual_backup(
        class_id=class_id,
        created_by=user.get("upn", "teacher"),
    )
    if not filepath:
        return RedirectResponse(
            f"/admin/classes/{class_id}/backups?msg={quote('Fehler beim Erstellen des Archivs')}",
            status_code=303,
        )
    _PENDING_ARCHIVES[class_id] = {"path": str(filepath), "downloaded": False}
    return RedirectResponse(
        f"/admin/classes/{class_id}/backups?msg={quote('Archiv erstellt — bitte jetzt herunterladen')}",
        status_code=303,
    )


@app.get("/admin/classes/{class_id}/archive/download")
async def archive_class_download(
    class_id: str,
    user: dict = Depends(auth.require_teacher_user),
):
    """Schritt 2: Archiv herunterladen (schaltet das Löschen frei)."""
    pending = _PENDING_ARCHIVES.get(class_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail="Kein Archiv vorbereitet — bitte zuerst erstellen",
        )
    path = Path(pending["path"])
    if not path.exists():
        _PENDING_ARCHIVES.pop(class_id, None)
        raise HTTPException(
            status_code=404,
            detail="Archiv-Datei nicht gefunden — bitte erneut erstellen",
        )
    cls = db.get_class(class_id)
    filename = f"archiv_{cls['name'] if cls else class_id}_{path.name}"
    pending["downloaded"] = True
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/admin/classes/{class_id}/archive/delete")
async def archive_class_delete(
    class_id: str,
    confirm_name: str = Form(...),
    user: dict = Depends(auth.require_teacher_user),
):
    """Schritt 3: Klasse nach erfolgtem Download endgültig löschen (Datenschutz)."""
    cls = db.get_class(class_id)
    if not cls:
        return RedirectResponse(
            f"/admin/classes?msg={quote('Klasse nicht gefunden')}", status_code=303
        )
    pending = _PENDING_ARCHIVES.get(class_id)
    if not pending or not pending.get("downloaded"):
        return RedirectResponse(
            f"/admin/classes/{class_id}/backups?msg={quote('Löschen blockiert: Archiv muss zuerst erstellt und heruntergeladen werden')}",
            status_code=303,
        )
    if confirm_name.strip() != cls["name"]:
        return RedirectResponse(
            f"/admin/classes/{class_id}/backups?msg={quote('Klassenname stimmt nicht überein — Löschen abgebrochen')}",
            status_code=303,
        )

    # DB-Löschung in einer Transaktion
    stats = db.delete_class_cascade(class_id)
    # Datei-Löschung erst nach erfolgreichem DB-Commit
    failed = backup.delete_class_backup_dirs(class_id)

    # In-Memory aufräumen
    _PENDING_ARCHIVES.pop(class_id, None)

    msg = (
        f"Klasse »{cls['name']}« archiviert und gelöscht: "
        f"{stats['members']} Schüler, {stats['einfach_records']} Unterrichts-, "
        f"{stats['nachweise']} Projekt-Einträge, {stats['active_ids']} Unterrichtsstand-Einträge"
    )
    if failed:
        msg += f" — ACHTUNG, manuell löschen: {', '.join(failed)}"
    return RedirectResponse(f"/admin/classes?msg={quote(msg)}", status_code=303)


@app.post("/admin/classes/orphans/delete")
async def admin_orphans_delete(user: dict = Depends(auth.require_teacher_user)):
    """Verwaiste Datensätze (ohne Klassenzuordnung) endgültig löschen."""
    counts = db.delete_orphaned_records()
    total = sum(counts.values())
    return RedirectResponse(
        f"/admin/classes?msg={quote(f'{total} verwaiste Datensätze gelöscht')}",
        status_code=303,
    )
```

- [ ] **Step 5: Smoke-Test (Server startet, Routen registriert)**

Run:
```bash
.venv/bin/python -c "
import main
paths = [r.path for r in main.app.routes]
for p in ['/admin/classes/{class_id}/archive',
          '/admin/classes/{class_id}/archive/download',
          '/admin/classes/{class_id}/archive/delete',
          '/admin/classes/orphans/delete']:
    assert p in paths, f'Route fehlt: {p}'
    print('Route OK:', p)
"
```
Expected: vier Zeilen `Route OK: ...`, kein Fehler. (Import von `main` ruft `db.init_db()` auf — Migration läuft dabei auf der lokalen Dev-DB; das ist gewollt.)

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "agent: Archiv-Routen (erstellen/download/loeschen) + Waisen-Endpunkt"
```

---

### Task 7: Templates — Archiv-Sektion und Waisen-Karte

**Files:**
- Modify: `templates/admin_class_backups.html`
- Modify: `templates/admin_classes.html`

**Interfaces:**
- Consumes: Template-Kontext `archive_pending` (None oder `{"path", "downloaded"}`), `cls.name`, `orphans`, `orphans_total` (Task 6)
- Produces: Drei-Schritt-UI (Erstellen → Download → Löschen mit Namensabfrage) und Waisen-Karte mit Bereinigen-Button

- [ ] **Step 1: Archiv-Sektion in `admin_class_backups.html`**

Direkt nach dem Block „Neues Backup erstellen" (nach Zeile 19, vor `<h2 ...>Vorhandene Backups`) einfügen:

```html
<h2 style="margin-top:1.5rem">Klasse archivieren (Schuljahresende)</h2>
<div class="info-notice" style="margin-bottom:.75rem">
  <strong>Ablauf:</strong> 1. Archiv erstellen → 2. Archiv herunterladen → 3. Klasse endgültig löschen.
  Beim Löschen werden <strong>alle</strong> Schülerdaten und <strong>alle</strong> Backup-Dateien
  dieser Klasse unwiderruflich vom Server entfernt (Datenschutz). Das heruntergeladene Archiv
  bleibt nur lokal bei dir erhalten.
</div>

{% if not archive_pending %}
<form method="post" action="/admin/classes/{{ cls.id }}/archive" style="display:inline">
  <button type="submit">1. Archiv erstellen</button>
</form>
{% else %}
<a href="/admin/classes/{{ cls.id }}/archive/download" class="button">2. Archiv herunterladen</a>
{% if archive_pending.downloaded %}
  <span class="badge badge-info" style="margin-left:.5rem">✓ Heruntergeladen — Löschen freigegeben</span>
{% else %}
  <span class="badge badge-muted" style="margin-left:.5rem">Download ausstehend — Löschen noch gesperrt</span>
{% endif %}

<form method="post" action="/admin/classes/{{ cls.id }}/archive/delete"
      style="margin-top:1rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap"
      onsubmit="return confirmArchiveDelete(this, {{ cls.name | tojson }})">
  <input type="text" name="confirm_name" placeholder="Klassenname »{{ cls.name }}« eintippen"
         required style="width:18rem">
  <button type="submit" class="btn-danger"
          {% if not archive_pending.downloaded %}disabled title="Erst das Archiv herunterladen"{% endif %}>
    3. Klasse endgültig löschen
  </button>
</form>
{% endif %}

<script>
function confirmArchiveDelete(form, className) {
  if (form.confirm_name.value.trim() !== className) {
    alert('Der eingegebene Name stimmt nicht mit dem Klassennamen »' + className + '« überein.');
    return false;
  }
  return confirm('Klasse »' + className + '« wirklich ENDGÜLTIG löschen?\n\n' +
    'Alle Schülerdaten und alle Backup-Dateien dieser Klasse werden unwiderruflich vom Server entfernt!');
}
</script>
```

- [ ] **Step 2: Waisen-Karte in `admin_classes.html`**

Direkt nach dem `{% if msg %}`-Block (Zeile 9) einfügen:

```html
{% if orphans_total and orphans_total > 0 %}
<div class="warning-notice" style="background:#fff4ce;border:1px solid #f0c36d;border-radius:.375rem;padding:.75rem 1rem;margin-bottom:1rem">
  <strong>Verwaiste Datensätze ohne Klassenzuordnung:</strong>
  Unterricht: {{ orphans.einfach_records }},
  Projekte: {{ orphans.nachweise }},
  Testanfragen: {{ orphans.test_requests }},
  Anträge: {{ orphans.kompetenzantraege }},
  Testzähler: {{ orphans.test_counters }}
  <form method="post" action="/admin/classes/orphans/delete" style="display:inline;margin-left:.5rem"
        onsubmit="return confirm('{{ orphans_total }} verwaiste Datensätze endgültig löschen? Dies kann nicht rückgängig gemacht werden.')">
    <button type="submit" class="btn-danger btn-sm">Bereinigen</button>
  </form>
</div>
{% endif %}
```

- [ ] **Step 3: Manueller Browser-Test (DEV_MODE)**

Run: `.venv/bin/uvicorn main:app --reload` (im Hintergrund), dann Browser:

1. `/dev-login` als `lehrer@schule.de` → `/admin/classes`
2. Testklasse „Archivtest" anlegen, öffnen → Mitglieder: 2 Schüler hinzufügen
3. Als Schüler bzw. über Lehrer-Ansicht Kompetenzen vergeben (mindestens 1 Unterricht + 1 Projekt) — oder über Restore eines Backups aus `_samples/`
4. `/admin/classes/{id}/backups`: „1. Archiv erstellen" klicken → Download-Button erscheint, Löschen-Button ist disabled
5. „2. Archiv herunterladen" → Datei enthält `students[].einfach` UND `students[].niveau`; Seite zeigt „✓ Heruntergeladen"
6. Falschen Namen eintippen → Browser-Alert, kein Submit
7. Korrekten Namen eintippen → Confirm → Redirect zu `/admin/classes` mit Erfolgsmeldung; Klasse ist weg
8. DB-Check: `.venv/bin/python -c "import sqlite3;con=sqlite3.connect('dashboard.db');print(con.execute(\"SELECT COUNT(*) FROM einfach_records WHERE class_id NOT IN (SELECT id FROM classes)\").fetchone())"` → `0` (keine Reste; Achtung: vorher Server-Prozess nicht nötig zu stoppen, SQLite verträgt parallele Reads)
9. `_backup/auto/` und `_backup/manual/` enthalten kein Verzeichnis der Testklasse mehr

Expected: alle Schritte wie beschrieben.

- [ ] **Step 4: Commit**

```bash
git add templates/admin_class_backups.html templates/admin_classes.html
git commit -m "agent: Archiv-UI (3 Schritte) und Waisen-Karte in Admin-Templates"
```

---

### Task 8: E2E-Verifikation auf DB-Kopie + Doku

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: alle vorherigen Tasks
- Produces: aktualisierte Doku; verifizierte Migration auf echter Datenkopie

- [ ] **Step 1: Migration + Löschung gegen Kopie der Produktiv-DB**

Run:
```bash
cp dashboard.db /tmp/e2e-test.db
.venv/bin/python - <<'EOF'
from pathlib import Path
import sqlite3
import db

db.DB_PATH = Path("/tmp/e2e-test.db")
db.init_db()  # Migration läuft

con = sqlite3.connect("/tmp/e2e-test.db")
con.row_factory = sqlite3.Row
# Pro Klasse: Anzahl Zeilen vorher/nachher
classes = [r["id"] for r in con.execute("SELECT id FROM classes")]
print("Klassen:", classes)
if classes:
    victim = classes[0]
    for t in ("einfach_records", "nachweise", "test_requests", "kompetenzantraege"):
        n = con.execute(f"SELECT COUNT(*) c FROM {t} WHERE class_id=?", (victim,)).fetchone()["c"]
        print(f"  {t} mit class_id={victim}: {n}")
    stats = db.delete_class_cascade(victim)
    print("Kaskaden-Stats:", stats)
    rest = con.execute(
        "SELECT COUNT(*) c FROM einfach_records WHERE class_id=?", (victim,)).fetchone()["c"]
    assert rest == 0, "Reste nach Löschung!"
    assert con.execute("SELECT COUNT(*) c FROM classes WHERE id=?", (victim,)).fetchone()[0] == 0
    print("E2E auf DB-Kopie OK")
EOF
rm /tmp/e2e-test.db
```
Expected: `E2E auf DB-Kopie OK`; Waisen-Counts ggf. sichtbar (echte Alt-Daten).

- [ ] **Step 2: `AGENTS.md` aktualisieren**

Zwei Änderungen:

1. Im Abschnitt „Data Model" die Tabelle „Core Tables (SQLite)": bei den vier Tabellen `einfach_records`, `nachweise`, `test_requests`, `kompetenzantraege` die Spalte „Purpose" jeweils um den Hinweis ergänzen, dass sie jetzt eine `class_id`-Spalte tragen (z. B. `... (student_id, class_id, competency_id, achieved)`).

2. Neuen Abschnitt nach „### Bulk Competency Assignment" einfügen:

```markdown
### Class Archiving (Schuljahresende)

Teachers can archive a class at the end of the school year from the class backups page:

1. **Archiv erstellen** — creates a final backup (standard backup JSON format, includes both Unterricht/einfach and Projekte/niveau)
2. **Archiv herunterladen** — mandatory download; unlocks deletion (tracked in-memory via `_PENDING_ARCHIVES`)
3. **Klasse endgültig löschen** — requires typing the class name; deletes ALL class data in one transaction (`db.delete_class_cascade`) plus all backup files (`backup.delete_class_backup_dirs`)

**Privacy:** No personal data remains on the server after deletion (student names, UPNs, competency records, evidence URLs, OneNote sync config/history, backup files).

**Orphan cleanup:** `/admin/classes` shows a warning card when records without class assignment exist (leftovers from the legacy delete); `db.count_orphaned_records()` / `db.delete_orphaned_records()` power it.

**Implementation:**
- Routes: `POST /admin/classes/{class_id}/archive`, `GET .../archive/download`, `POST .../archive/delete`, `POST /admin/classes/orphans/delete`
- Migration: `_migrate_add_class_ids()` in `db.py` adds `class_id` to `einfach_records` (new PK `(student_id, class_id, competency_id)`), `nachweise`, `test_requests`, `kompetenzantraege`
- Write paths derive `class_id` from `class_members` (`_class_id_for_student`), explicit override possible
- Templates: `templates/admin_class_backups.html`, `templates/admin_classes.html`
```

- [ ] **Step 3: Abschließender Server-Neustart-Test**

Run: `.venv/bin/uvicorn main:app --reload` — prüfen: Server startet ohne Fehler, Migration-Meldung im Log (oder nichts, wenn schon migriert), Dashboard für `anna@schule.de` zeigt weiterhin ihre Kompetenzen (Regression: Lesepfade unverändert).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "agent: Doku Klassen-Archivierung und class_id-Konvention"
```

---

## Bekannte Grenzen / Follow-ups (nicht Teil dieses Plans)

- Der alte Schnell-Löschen-Button (`POST /admin/classes/delete`, `db.delete_class`) bleibt unverändert und erzeugt weiterhin Waisen — diese werden jetzt durch die Waisen-Karte sichtbar und bereinigbar. Perspektivisch: Button auf Kaskade umstellen oder entfernen.
- `teacher_tokens` (Klartext-Refresh-Tokens), `server.log` mit UPNs, `backup_onenote_*.json` im Projektroot: manuelle Bereinigung durch den User bzw. separates Härtungsthema.
- `_TEST_PREVIEWS` (In-Memory) wird bei der Archiv-Löschung nicht bereinigt, weil die Einträge keinen Klassenbezug speichern; sie sind flüchtig (weg bei Neustart). Bei späterem Bedarf `class_id` in den Preview-Einträgen ergänzen und in `archive_class_delete` bereinigen.
- Echte Mehrfachmitgliedschaft im UI (Schüler in mehreren Fächern) ist durch das Schema vorbereitet, aber kein UI dafür gebaut.
