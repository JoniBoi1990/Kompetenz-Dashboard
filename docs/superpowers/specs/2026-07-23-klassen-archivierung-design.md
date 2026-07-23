# Design: Klassen-Archivierung zum Schuljahresende

**Datum:** 2026-07-23
**Status:** Freigegeben durch User (Brainstorming abgeschlossen)
**Branch:** `agent-dev`

---

## 1. Kontext & Ziel

Zum Schuljahresende sollen Klassen archiviert werden können:

1. Der **letzte Stand** der Klasse wird als JSON-Datei im **bestehenden Backup-Format** heruntergeladen.
2. Danach wird die Klasse **vollständig vom Server gelöscht** — Datenbank-Zeilen **und** Backup-Dateien.
3. **Datenschutzziel:** Nach der Löschung verbleiben keine personenbezogenen Daten (Namen, UPNs) und keine sensiblen Daten (Kompetenzstände, Noten-Grundlagen, Evidence-URLs) der Klasse auf dem Server.

### Ausgangslage (aus Code-Analyse)

- Schülerdaten-Tabellen (`einfach_records`, `nachweise`, `test_requests`, `kompetenzantraege`) haben **kein `class_id`** — der Klassenbezug existiert nur indirekt über `class_members`.
- Die bestehende `db.delete_class()` (`db.py:708`) löscht nur `class_members` + `classes`-Zeile und lässt alle Schülerdaten, `active_ids`, OneNote-Daten und Backup-Dateien zurück.
- `backup.create_backup()` (`backup.py:58`) exportiert bereits pro Schüler **beide** Kompetenztypen: `einfach` (Unterricht) und `niveau` (Projekte, inkl. Level und Nachweis-URLs). Das Archiv nutzt dieses Format unverändert.
- Benennungs-Klarstellung: `einfach_records` = Unterrichts-Kompetenzen, `nachweise` = Projekt-/Niveau-Kompetenzen (mit `niveau_level`, `evidence_url`).

## 2. Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|---|---|
| Ansatz | **A:** `class_id`-Migration + Archiv-Flow (Fundament für spätere Mehrfachmitgliedschaft, z. B. mehrere Fächer) |
| Ablauf | **Zweistufig:** Download erzwingen, dann Löschen (mit Eintippen des Klassennamens) |
| Waisen-Bereinigung | **Fester Bestandteil** des Features (nicht optional) |
| Test-Counter | `test_counters` bleibt global (kein `class_id`); Zeile wird gelöscht, wenn letzte Mitgliedschaft des Schülers endet |
| Berechtigung | Wie bisher: `/admin/*` für alle Lehrkräfte (Bestandskonvention, keine neue Rolle) |

## 3. Teil 1: Schema-Migration (`class_id`)

### 3.1 Neue Spalten

`class_id TEXT` (nullable) in vier Tabellen:

- `einfach_records` (Unterricht)
- `nachweise` (Projekte/Niveau)
- `test_requests`
- `kompetenzantraege`

`test_counters` erhält **kein** `class_id` (nur laufende Testnummer pro Schüler).

### 3.2 `einfach_records`: Neuer Primärschlüssel

Die Tabelle wird neu aufgebaut mit PK `(student_id, class_id, competency_id)` statt `(student_id, competency_id)` — sonst kollidieren später Parallelklassen mit geteilter Kompetenzliste. Vorgehen (SQLite-Standard): neue Tabelle erstellen, Daten kopieren, alte Tabelle droppen, umbenennen.

### 3.3 Migrationsablauf

- Läuft beim Serverstart in `init_db()`, im Muster der bestehenden Migration `_migrate_competency_ids_to_text()` (`db.py:175`): Prüfung via `PRAGMA table_info`, ob Spalte fehlt → `ALTER TABLE` bzw. Tabellen-Neuaufbau → Backfill.
- **Backfill:** `class_id` aus `class_members` ableiten (jeder Schüler ist aktuell in genau einer Klasse).
- **Waisen:** Zeilen, deren `student_id` keine Mitgliedschaft hat (Relikte früherer unvollständiger Löschungen), bleiben `class_id = NULL`. Die Migration **loggt Anzahl und betroffene Tabellen** ins Server-Log. Bereinigung siehe Teil 4.

### 3.4 Schreibpfade

Die `db.py`-Funktionen leiten `class_id` **intern** über eine Hilfsfunktion `_class_id_for_student(con, student_id)` aus `class_members` ab:

- `upsert_einfach` (`db.py:343`), `add_nachweis` (`db.py:389`), `save_test_request` (`db.py:458`), `save_kompetenzantrag` (`db.py:534`), `bulk_upsert_einfach` (`db.py:995`), `bulk_add_nachweise` (`db.py:1037`)

Dadurch bleiben die Aufrufstellen in `main.py` und `onenote_sync.py` **unverändert**. Einzige Ausnahme: `backup.restore_backup()` übergibt `class_id` explizit (beim Restore ist die Klasse bekannt, ggf. Mitgliedschaft noch nicht angelegt).

### 3.5 Lesepfade

Bleiben unverändert (Abfrage per `student_id`). Die Ein-Klassen-Annahme im UI bleibt vorerst bestehen; Mehrfachmitgliedschaft ist ein späteres separates Projekt.

## 4. Teil 2: Archiv-Flow (zweistufig)

Platzierung auf der bestehenden Seite **`/admin/classes/{class_id}/backups`** (`main.py:3204`), Template `templates/admin_class_backups.html`.

### Schritt 1 — „Archiv erstellen"

- `POST /admin/classes/{class_id}/archive`
- Erzeugt das Backup: `backup.create_backup(class_id, created_by=<Lehrer-UPN>)` + `backup.save_backup(data, manual=True)`
- Server-seitiger Pending-State (In-Memory): `_PENDING_ARCHIVES[class_id] = {"path": <Path>, "downloaded": False}`
- Seite zeigt danach Download-Button + Hinweis, dass Löschen erst nach Download möglich ist.

### Schritt 2 — Download (Pflicht)

- Download der Archiv-Datei über eine dedizierte Route `GET /admin/classes/{class_id}/archive/download` (liefert die Datei aus `_PENDING_ARCHIVES`, setzt `downloaded = True`).
- Ohne gesetztes Flag bleibt der Löschen-Button deaktiviert (Button disabled + serverseitige Prüfung).

### Schritt 3 — „Klasse endgültig löschen"

- Modal im Template: verlangt **Eintippen des exakten Klassennamens** (Client-Vergleich + serverseitige Prüfung).
- `POST /admin/classes/{class_id}/archive/delete` prüft: Klasse existiert, `_PENDING_ARCHIVES[class_id].downloaded == True`, eingegebener Name == Klassenname.

**Lösch-Kaskade (DB, eine Transaktion, in dieser Reihenfolge):**

1. `DELETE FROM einfach_records WHERE class_id = ?`
2. `DELETE FROM nachweise WHERE class_id = ?`
3. `DELETE FROM test_requests WHERE class_id = ?`
4. `DELETE FROM kompetenzantraege WHERE class_id = ?`
5. `DELETE FROM active_ids WHERE class_id = ?`
6. OneNote: `db.delete_onenote_sync_config(class_id)` (löscht Config + History, `db.py:1297`)
7. `class_members`-Zeilen der Klasse löschen; **danach** pro ehemaligem Mitglied prüfen, ob es noch in einer anderen Klasse Mitglied ist
8. `DELETE FROM test_counters WHERE student_id = ?` nur für Schüler, die nach Schritt 7 **keine** weitere Mitgliedschaft mehr haben
9. `classes`-Zeile löschen

**Dateisystem (nach erfolgreichem Commit):**

- `_backup/auto/{class_id}/` und `_backup/manual/{class_id}/` rekursiv entfernen — **inklusive der eben erstellten Archiv-Datei** (sie existiert dann nur noch lokal beim Lehrer). Pfad-Sicherheitscheck im Muster von `backup.delete_backup()` (`backup.py:469`): Pfade müssen innerhalb von `BACKUP_DIR` liegen.

**In-Memory:**

- `_TEST_PREVIEWS`-Einträge der Klasse verwerfen, `_PENDING_ARCHIVES[class_id]` entfernen.

**Abschluss:** Redirect zu `/admin/classes` mit Erfolgsmeldung (Anzahl gelöschter Datensätze/Dateien).

## 5. Teil 3: Fehlerbehandlung & Sicherheit

- **Transaktion:** Gesamte DB-Löschung in einer Transaktion — bei Fehler Rollback, kein Halbzustand. Datei-Löschung erst nach Commit.
- **Datei-Löschung schlägt fehl:** Klasse ist dann aus der DB entfernt, Restdateien wären ein Datenschutzproblem → Fehlermeldung nennt die konkreten verbliebenen Pfade zur manuellen Entfernung.
- **Race-Conditions:** OneNote-Sync (02:00 UTC) / Auto-Backup (03:00 UTC) könnten theoretisch parallel laufen. Durch die Transaktion blockiert SQLite kurz; da die OneNote-Config in derselben Transaktion gelöscht wird, kann der Sync die Klasse nicht „wiederbeleben". Transaktion kurz halten (Datei-I/O außerhalb).
- **Idempotenz:** Endpunkt prüft zu Beginn Existenz der Klasse + Download-Flag; Doppelklick/Zweitaufruf liefert saubere Fehlermeldung.
- **Flüchtiger Pending-State:** Nach Server-Neustart ist `_PENDING_ARCHIVES` leer → Archiv einfach erneut erstellen (unkritisch, kein Datenverlust).
- **Kein Zugriff für Schüler:** Alle neuen Routen unter `/admin/*` mit bestehendem `require_teacher_user`.

## 6. Teil 4: Waisen-Bereinigung (fester Bestandteil)

Frühere Klassen-Löschungen haben Schülerdaten zurückgelassen. Nach der Migration sind das Zeilen mit `class_id IS NULL` in den vier Tabellen sowie `test_counters`-Zeilen von Schülern ohne jede Mitgliedschaft.

- **Anzeige:** Auf `/admin/classes` eine kompakte Karte „Verwaiste Datensätze" mit Anzahl pro Tabelle (nur sichtbar, wenn > 0).
- **Bereinigung:** Button „Verwaiste Datensätze löschen" mit Bestätigungs-Dialog (kein Klassenname nötig, aber explizite Bestätigung). Löscht:
  - `DELETE FROM einfach_records WHERE class_id IS NULL`
  - `DELETE FROM nachweise WHERE class_id IS NULL`
  - `DELETE FROM test_requests WHERE class_id IS NULL`
  - `DELETE FROM kompetenzantraege WHERE class_id IS NULL`
  - `DELETE FROM test_counters WHERE student_id NOT IN (SELECT student_id FROM class_members)`
- Neue db-Funktionen: `count_orphaned_records() -> dict`, `delete_orphaned_records() -> dict` (liefert gelöschte Anzahlen für die Erfolgsmeldung).

## 7. Testing (manuell, kein Test-Framework im Projekt)

Checkliste (DEV_MODE):

1. **Migration auf Datenkopie:** Lokale Kopie der echten `dashboard.db`, Server starten, Log prüfen (Backfill-Anzahl, Waisen-Meldung), Stichproben: `SELECT class_id, COUNT(*) FROM einfach_records GROUP BY class_id`.
2. **Archiv-Flow Ende-zu-Ende:** Testklasse mit Schülern + Kompetenzen (einfach **und** niveau) anlegen → Archiv erstellen → JSON-Inhalt prüfen (beide Typen vorhanden, `students[].einfach` + `students[].niveau`) → Löschen ohne Download muss blockiert werden → Download → Löschen mit falschem Klassennamen muss scheitern → Löschen mit korrektem Namen.
3. **Verifikation nach Löschung:** DB-Abfragen auf alle betroffenen Tabellen (`class_id`), `test_counters` der Ex-Mitglieder, `_backup/`-Verzeichnisse weg, OneNote-Config/History weg.
4. **Mehrfachmitgliedschaft simulieren:** Schüler in zwei Klassen, eine Klasse archivieren → Daten der anderen Klasse müssen intakt bleiben (nur Zeilen mit gelöschter `class_id` weg; `test_counters` bleibt).
5. **Regression:** Normale Nutzung nach Migration (Kompetenz vergeben, Nachweis anlegen, Testanfrage, OneNote-Sync, Restore aus Backup) — prüfen, dass `class_id` korrekt gesetzt wird.
6. **Waisen-Bereinigung:** Karte erscheint mit korrekten Zahlen, Löschen entfernt nur NULL-Zeilen.

## 8. Datenschutz-Befunde & begleitende Maßnahmen

1. **`.gitignore`-Lücke (wird in diesem Feature geschlossen):** `_backup/`, `backup_onenote_*.json`, `dashboard.db.backup.*` ergänzen — verhindert versehentliches Committen von Personendaten.
2. **Bestehende Dateien mit echten Personendaten (manueller Schritt durch User, nicht Teil des Codes):** `backup_onenote_2026-03-28_*.json`, `dashboard.db.backup.20260319_230528`, `_backup/20260319/dashboard.db` — Empfehlung: lokal sichern und vom Server/Repo entfernen.
3. **Nur dokumentiert (kein Code in diesem Feature):**
   - `teacher_tokens` speichert Refresh-Tokens im Klartext → separates Härtungsthema.
   - `server.log` kann Namen/UPNs in URLs enthalten (auf dem Server: journalctl).
   - `PRAGMA foreign_keys` ist nicht aktiviert; FK-Cascades wirken nicht → bewusst kein Umbau in diesem Feature.
   - OneNote-seitige Daten (Klassen-Notebooks in Microsoft 365) werden vom Feature nicht berührt — Löschung dort ist separate organisatorische Aufgabe.

## 9. Nicht-Ziele (Out of Scope)

- UI/Logik für echte Mehrfachmitgliedschaft (mehrere Fächer gleichzeitig) — die Migration legt nur das Daten-Fundament.
- Verschlüsselung von `teacher_tokens`.
- Admin-Rollenkonzept (Trennung Admin/Lehrer).
- Automatische Archivierung nach Zeitplan (bleibt manueller Lehrer-Schritt).

## 10. Betroffene Dateien (Übersicht)

| Datei | Änderung |
|---|---|
| `db.py` | Migration in `init_db()`, `_class_id_for_student()`, Schreibfunktionen, `count_orphaned_records()`, `delete_orphaned_records()`, `delete_class_cascade()` |
| `backup.py` | Hilfsfunktion `delete_class_backup_dirs(class_id)` mit Pfad-Check |
| `main.py` | `_PENDING_ARCHIVES`, Routen `/archive`, `/archive/download`, `/archive/delete`, Waisen-Endpunkt, Counts fürs Template |
| `templates/admin_class_backups.html` | Archiv-Sektion: Erstellen-Button, Download-Button, Lösch-Modal |
| `templates/admin_classes.html` | Waisen-Karte mit Anzahlen + Lösch-Button |
| `.gitignore` | `_backup/`, `backup_onenote_*.json`, `dashboard.db.backup.*` |
| `AGENTS.md` | Dokumentation des Archiv-Features + `class_id`-Konvention |
