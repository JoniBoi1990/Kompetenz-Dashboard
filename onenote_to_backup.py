"""
onenote_to_backup.py — Liest das Klassennotizbuch aus OneNote und erzeugt eine
Backup-JSON-Datei, die direkt über /admin/classes/{class_id}/members/import
hochgeladen werden kann.

Abhängigkeiten (zusätzlich zu requirements.txt):
    pip install beautifulsoup4

Verwendung:
    python onenote_to_backup.py

Der Browser-Login (Device Flow) wird interaktiv abgefragt.
"""

# =============================================================================
# KONFIGURATION — hier anpassen
# =============================================================================

TENANT_ID = "89cd34a8-db37-49d2-a4f9-9231b59f7e1a"
CLIENT_ID = "2bdc4f83-10a9-428d-9224-2f841653effa"

SITE_URL = "https://birklehofde.sharepoint.com/sites/Kl.8ChKa2425"
NOTEBOOK_NAME = "9 Ch Ht 2526-Notizbuch"   # Exakter Name des Notizbuchs

# Dashboard-URL für ID-Abgleich (leer = lokale JSON-Datei als Fallback)
DASHBOARD_URL = "https://bhof.uber.space"

# Lokale Fallback-Datei für einfach (wird nur genutzt wenn Server nicht erreichbar)
COMPETENCY_LIST_FILE = "kompetenzlisten/klasse-9-chemie.json"

# Metadaten für das Backup
CLASS_ID = "ceadfc53-502a-4763-a120-0e249cad609e"
CLASS_NAME = "9"
GRADE_LEVEL = 9
COMPETENCY_LIST_ID = "klasse-9-chemie"
CREATED_BY = "lehrer@schule.de"

# Schülernamen (wie im OneNote-Abschnittsnamen) → UPN/E-Mail im Dashboard
STUDENT_UPN_MAP: dict[str, str] = {
    "Brunet-Moret, Leopold":            "Leopold.Brunet-Moret@s.birklehof.de",
    "Chu , Ngoc Anh Eva":               "ngocanheva.chu@s.birklehof.de",       # ⚠ mehrere Vornamen — bitte prüfen
    "Czech, Amelie":                    "Amelie.Czech@s.birklehof.de",
    "Dreyer, Sören":                    "Soeren.Dreyer@s.birklehof.de",        # ⚠ Umlaut — bitte prüfen
    "Eckert, Rafael William Thomas":    "Rafael.Eckert@s.birklehof.de",        # ⚠ erster Vorname — bitte prüfen
    "Egger, Thais":                     "Thais.Egger@s.birklehof.de",
    "Finke, Louis":                     "Louis.Finke@s.birklehof.de",
    "Götte, Levi":                      "Levi.Goette@s.birklehof.de",          # ⚠ Umlaut — bitte prüfen
    "Heinkel, Sarah":                   "Sarah.Heinkel@s.birklehof.de",
    "Isabel Sänger":                    "Isabel.Saenger@s.birklehof.de",       # ⚠ Umlaut — bitte prüfen
    "Komiljonov, Firdavs":              "Firdavs.Komiljonov@s.birklehof.de",
    "Liu, Tianshuo (Leo)":              "Tianshuo.Liu@s.birklehof.de",         # ⚠ Spitzname ignoriert — bitte prüfen
    "Metzeroth, Kaleb":                 "Kaleb.Metzeroth@s.birklehof.de",
    "Moltke, Leopold von":              "Leopold.von.Moltke@s.birklehof.de",    # ⚠ Adelsprädikat — bitte prüfen
    "Pöllath, Tom":                     "Tom.Poellath@s.birklehof.de",         # ⚠ Umlaut — bitte prüfen
    "Rennscheidt, Marlon":              "Marlon.Rennscheidt@s.birklehof.de",
    "Senghaas, Dinah":                  "Dinah.Senghaas@s.birklehof.de",
    "Shcherbak, Diana":                 "Diana.Shcherbak@s.birklehof.de",
    "Shen, Zhengqi (Kai)":              "Zhengqi.Shen@s.birklehof.de",         # ⚠ Spitzname ignoriert — bitte prüfen
    "Stenianskyi, Artem":               "Artem.Stenianskyi@s.birklehof.de",
    "Vollmer, Junes":                   "Junes.Vollmer@s.birklehof.de",
    "Wang, Qi":                         "Qi.Wang@s.birklehof.de",
    "Test Schueler_haut":               "Test.Schueler_haut@s.birklehof.de",
}

# =============================================================================
# SKRIPT — ab hier nichts ändern
# =============================================================================

import json
import sys
import re
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import msal
except ImportError:
    sys.exit("Fehler: msal nicht installiert. Bitte: pip install msal")

try:
    import httpx
except ImportError:
    sys.exit("Fehler: httpx nicht installiert. Bitte: pip install httpx")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Fehler: beautifulsoup4 nicht installiert. Bitte: pip install beautifulsoup4")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Notes.Read.All"]


# ---------------------------------------------------------------------------
# Authentifizierung
# ---------------------------------------------------------------------------

def get_token() -> str:
    if not TENANT_ID or not CLIENT_ID:
        sys.exit(
            "Fehler: TENANT_ID und CLIENT_ID müssen im Skript eingetragen werden.\n"
            "Diese findest du im Azure Portal unter App-Registrierungen."
        )
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )
    # Cached token versuchen
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("Token aus Cache geladen.")
            return result["access_token"]

    # Device Flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        sys.exit(f"Device Flow fehlgeschlagen: {flow}")
    print("\n" + "=" * 60)
    print(flow["message"])
    print("=" * 60 + "\n")
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        sys.exit(f"Login fehlgeschlagen: {result.get('error_description', result)}")
    print("Login erfolgreich.\n")
    return result["access_token"]


# ---------------------------------------------------------------------------
# Graph API Hilfsfunktionen
# ---------------------------------------------------------------------------

def graph_get(token: str, path: str, **params) -> dict:
    url = path if path.startswith("https://") else f"{GRAPH_BASE}{path}"
    for attempt in range(4):
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or None,
            timeout=30,
        )
        if r.status_code in (429, 500, 502, 503, 504):
            wait = int(r.headers.get("Retry-After", 2 ** attempt))
            print(f"  ⏳ Graph API {r.status_code} — warte {wait}s (Versuch {attempt + 1}/4)")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()  # letzter Versuch schlägt durch
    return r.json()


def get_page_html(token: str, page_id: str, onenote_prefix: str) -> str:
    url = f"{GRAPH_BASE}{onenote_prefix}/pages/{page_id}/content"
    r = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------------------
# SharePoint Site-ID ermitteln
# ---------------------------------------------------------------------------

def get_site_id(token: str) -> str:
    # SITE_URL → hostname + path
    # z.B. https://birklehofde.sharepoint.com/sites/Kl.8ChKa2425
    url = SITE_URL.rstrip("/")
    # Extrahiere host und Pfad
    match = re.match(r"https://([^/]+)(/.+)", url)
    if not match:
        sys.exit(f"Ungültige SITE_URL: {SITE_URL}")
    host, path = match.group(1), match.group(2)
    data = graph_get(token, f"/sites/{host}:{path}")
    site_id = data.get("id", "")
    if not site_id:
        sys.exit("Site-ID konnte nicht ermittelt werden.")
    print(f"Site-ID: {site_id}")
    return site_id


# ---------------------------------------------------------------------------
# Notizbuch und Abschnitte laden
# ---------------------------------------------------------------------------

def find_notebook(token: str, site_id: str) -> tuple[str, str]:
    """Gibt (notebook_id, base_prefix) zurück, wobei base_prefix der API-Pfad-Präfix ist."""
    candidates = [
        ("/me/onenote/notebooks", "/me/onenote"),
        (f"/sites/{site_id}/onenote/notebooks", f"/sites/{site_id}/onenote"),
    ]
    all_names: list[str] = []
    for list_endpoint, prefix in candidates:
        try:
            data = graph_get(token, list_endpoint)
            notebooks = data.get("value", [])
            for nb in notebooks:
                name = nb.get("displayName", "").strip()
                all_names.append(name)
                if name == NOTEBOOK_NAME.strip():
                    print(f"Notizbuch gefunden: {name} (ID: {nb['id']})")
                    return nb["id"], prefix
        except Exception:
            continue
    sys.exit(
        f"Notizbuch '{NOTEBOOK_NAME}' nicht gefunden.\n"
        f"Verfügbare Notizbücher: {all_names}"
    )


def get_student_section_groups(token: str, notebook_id: str, onenote_prefix: str) -> list[dict]:
    """Gibt Abschnittsgruppen zurück (= Schüler im Klassennotizbuch)."""
    data = graph_get(token, f"{onenote_prefix}/notebooks/{notebook_id}/sectionGroups")
    groups = data.get("value", [])
    if groups:
        print(f"{len(groups)} Schüler-Abschnittsgruppen gefunden.")
        return groups
    # Fallback: direkte Abschnitte (falls kein Abschnittsgruppen-Layout)
    data = graph_get(token, f"{onenote_prefix}/notebooks/{notebook_id}/sections")
    sections = data.get("value", [])
    print(f"{len(sections)} direkte Abschnitte gefunden (kein Abschnittsgruppen-Layout).")
    return sections


def get_sections_in_group(token: str, group_id: str, onenote_prefix: str) -> list[dict]:
    """Gibt Abschnitte innerhalb einer Schüler-Abschnittsgruppe zurück."""
    data = graph_get(token, f"{onenote_prefix}/sectionGroups/{group_id}/sections")
    return data.get("value", [])


def find_page_in_section(token: str, section_id: str, page_title: str, onenote_prefix: str) -> str | None:
    data = graph_get(token, f"{onenote_prefix}/sections/{section_id}/pages")
    pages = data.get("value", [])
    for p in pages:
        if p.get("title", "").strip().lower() == page_title.strip().lower():
            return p["id"]
    return None


# ---------------------------------------------------------------------------
# Kompetenzliste laden und Mapping aufbauen
# ---------------------------------------------------------------------------

def _fetch_list_from_server(list_id: str) -> list[dict]:
    """Lädt eine Kompetenzliste vom Dashboard-Server. Gibt [] zurück bei Fehler."""
    url = f"{DASHBOARD_URL}/api/competencies/{list_id}"
    try:
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            return response.json()
        print(f"  ⚠ Server antwortete mit {response.status_code} für {list_id}")
    except Exception as e:
        print(f"  ⚠ Server nicht erreichbar ({e})")
    return []


def _fetch_class_lists() -> tuple[str | None, str | None]:
    """
    Fragt den Server nach den aktiven Kompetenzlisten-IDs für CLASS_ID.
    Gibt (einfach_list_id, niveau_list_id) zurück; None wenn nicht verfügbar.
    """
    url = f"{DASHBOARD_URL}/api/class/{CLASS_ID}/lists"
    try:
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            return data.get("einfach_list_id"), data.get("niveau_list_id")
        print(f"  ⚠ Klassen-Listen nicht abfragbar (HTTP {response.status_code})")
    except Exception as e:
        print(f"  ⚠ Server nicht erreichbar für Klassen-Listen ({e})")
    return None, None


def load_competency_list() -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Gibt zwei Dicts zurück:
      einfach_by_name: {normalized_name: competency_dict}
      niveau_by_name:  {normalized_name: competency_dict}

    Fragt zuerst den Server nach den aktiven Listen-IDs der Klasse (CLASS_ID),
    lädt dann die Kompetenzlisten vom Server.
    Fallback: lokale JSON-Datei wenn Server nicht erreichbar.
    """
    # Aktive Listen-IDs vom Server holen
    einfach_list_id, niveau_list_id = None, None
    if DASHBOARD_URL and CLASS_ID:
        print(f"Aktive Listen für Klasse {CLASS_ID} vom Server abfragen …")
        einfach_list_id, niveau_list_id = _fetch_class_lists()
        if einfach_list_id or niveau_list_id:
            print(f"  → Einfach: {einfach_list_id}  |  Niveau: {niveau_list_id}")

    # --- Einfach ---
    einfach_raw: list[dict] = []
    if einfach_list_id:
        einfach_raw = _fetch_list_from_server(einfach_list_id)
        if einfach_raw:
            print(f"Einfach-Liste vom Server: {len(einfach_raw)} Einträge ({einfach_list_id})")
    if not einfach_raw:
        path = Path(COMPETENCY_LIST_FILE)
        if not path.exists():
            sys.exit(f"Einfach-Kompetenzliste nicht gefunden: {COMPETENCY_LIST_FILE}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        einfach_raw = [c for c in data.get("competencies", []) if c.get("typ") == "einfach"]
        print(f"Einfach-Liste aus lokaler Datei (Fallback): {len(einfach_raw)} Einträge")

    # --- Niveau ---
    niveau_raw: list[dict] = []
    if niveau_list_id:
        niveau_raw = _fetch_list_from_server(niveau_list_id)
        if niveau_raw:
            print(f"Niveau-Liste vom Server: {len(niveau_raw)} Einträge ({niveau_list_id})")
    if not niveau_raw:
        path = Path(COMPETENCY_LIST_FILE)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            niveau_raw = [c for c in data.get("competencies", []) if c.get("typ") == "niveau"]
            if niveau_raw:
                print(f"Niveau-Liste aus lokaler Datei (Fallback): {len(niveau_raw)} Einträge")
        if not niveau_raw:
            print("⚠ Keine Niveau-Liste verfügbar — Projektkompetenzen werden nicht gematcht")

    einfach = {_normalize(c["name"]): c for c in einfach_raw if c.get("typ") in ("einfach", None)}
    niveau  = {_normalize(c["name"]): c for c in niveau_raw  if c.get("typ") in ("niveau",  None)}
    print(f"  → {len(einfach)} einfach, {len(niveau)} niveau bereit.")
    return einfach, niveau


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def match_competency(text: str, lookup: dict[str, dict]) -> dict | None:
    """Findet eine Kompetenz per exaktem, Teilstring- oder Word-Overlap-Match."""
    key = _normalize(text)
    # 1. Exakter Match
    if key in lookup:
        return lookup[key]
    # 2. Substring-Match: OneNote-Text ist Teilstring des JSON-Namens oder umgekehrt
    for k, comp in lookup.items():
        if key in k or k in key:
            return comp
    # 3. Word-Overlap: ≥60% der Wörter des kürzeren Textes kommen im längeren vor
    key_words = set(key.split())
    if len(key_words) >= 3:
        best_score = 0.0
        best_comp = None
        for k, comp in lookup.items():
            k_words = set(k.split())
            shorter = key_words if len(key_words) <= len(k_words) else k_words
            longer = k_words if len(key_words) <= len(k_words) else key_words
            overlap = len(shorter & longer) / len(shorter)
            if overlap > best_score:
                best_score = overlap
                best_comp = comp
        if best_score >= 0.6:
            return best_comp
    return None


# ---------------------------------------------------------------------------
# HTML-Parser: Unterrichtskompetenzen (Checkboxen)
# ---------------------------------------------------------------------------

def parse_einfach_page(html: str, einfach_lookup: dict[str, dict]) -> dict[str, bool]:
    """
    Parst die Unterrichtskompetenzen-Tabelle:
      ID | Kompetenzformulierung | [Checkbox]
    Gibt {competency_id: True} für alle abgehakten Zeilen zurück.
    """
    soup = BeautifulSoup(html, "html.parser")
    achieved: dict[str, bool] = {}
    unmatched: list[str] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Header erkennen: suche Spalte mit "kompetenz" im Header
        header_cells = rows[0].find_all(["th", "td"])
        text_col: int | None = None
        for i, cell in enumerate(header_cells):
            h = _normalize(cell.get_text(strip=True))
            if "kompetenz" in h:
                text_col = i
                break
        if text_col is None:
            continue  # Nicht die richtige Tabelle

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= text_col:
                continue

            comp_text = re.sub(r"\s+", " ", cells[text_col].get_text(strip=True)).strip()
            if not comp_text:
                continue

            # Checkbox im letzten Cell oder irgendwo in der Zeile
            checkbox = cells[-1].find("input", {"type": "checkbox"})
            if checkbox is None:
                checkbox = row.find("input", {"type": "checkbox"})
            is_checked = checkbox is not None and checkbox.has_attr("checked")

            comp = match_competency(comp_text, einfach_lookup)
            if comp:
                if is_checked:
                    achieved[comp["id"]] = True
            elif is_checked:
                unmatched.append(comp_text)

    if unmatched:
        print(f"  ⚠ Nicht zugeordnete abgehakte Kompetenzen ({len(unmatched)}):")
        for u in unmatched[:10]:
            print(f"    - {u}")
        if len(unmatched) > 10:
            print(f"    ... und {len(unmatched) - 10} weitere")

    return achieved


# ---------------------------------------------------------------------------
# HTML-Parser: Projektkompetenzen (Tabelle)
# ---------------------------------------------------------------------------

NIVEAU_LABELS = {
    "experte": 3,
    "expert": 3,
    "advanced": 2,
    "fortgeschritten": 2,
    "beginner": 1,
    "anfänger": 1,
    "anfaenger": 1,
}


def parse_niveau_page(html: str, niveau_lookup: dict[str, dict]) -> dict[str, dict]:
    """
    Gibt {competency_id: {"level": int, "url": str|None}} zurück.
    Nur das höchste erreichte Niveau pro Kompetenz.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, dict] = {}
    unmatched: list[str] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Header-Zeile: Spaltenreihenfolge ermitteln
        header_cells = rows[0].find_all(["th", "td"])
        col_to_level: dict[int, int] = {}   # Spaltenindex → Niveau-Level
        comp_col: int | None = None          # Spaltenindex für Kompetenzname

        text_col: int | None = None
        for i, cell in enumerate(header_cells):
            header_text = _normalize(cell.get_text(strip=True))
            if header_text in NIVEAU_LABELS:
                col_to_level[i] = NIVEAU_LABELS[header_text]
            elif header_text in ("pbk", "kompetenz", "projektbasierte kompetenz") or (
                "kompetenz" in header_text and text_col is None
            ):
                text_col = i

        if not col_to_level:
            continue  # keine Niveau-Spalten erkannt → nicht unsere Tabelle

        # Fallback: text_col = Spalte vor der ersten Niveau-Spalte (meist col 1)
        if text_col is None:
            first_niveau_col = min(col_to_level.keys())
            text_col = max(0, first_niveau_col - 1)
            # Vermeide ID-Spalte (col 0 ist numerisch): bevorzuge col 1
            if text_col == 0 and first_niveau_col > 1:
                text_col = 1

        # Datenzeilen
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if not cells or len(cells) <= text_col:
                continue
            comp_name = cells[text_col].get_text(separator=" ", strip=True)
            comp_name = re.sub(r"\s+", " ", comp_name).strip()
            if not comp_name:
                continue

            comp = match_competency(comp_name, niveau_lookup)
            if not comp:
                unmatched.append(comp_name)
                continue

            # Höchstes erreichtes Niveau
            best_level = 0
            best_url: str | None = None
            for col_idx, level in col_to_level.items():
                if col_idx >= len(cells):
                    continue
                cell = cells[col_idx]
                cell_text = cell.get_text(separator=" ", strip=True)
                # Link in der Zelle?
                link = cell.find("a")
                url = link["href"] if link and link.has_attr("href") else None
                if cell_text or url:
                    if level > best_level:
                        best_level = level
                        best_url = url or cell_text or None

            if best_level > 0:
                result[comp["id"]] = {"level": best_level, "url": best_url}

    if unmatched:
        unique = list(dict.fromkeys(unmatched))
        print(f"  ⚠ Nicht zugeordnete Niveau-Kompetenzen ({len(unique)}):")
        for u in unique[:10]:
            print(f"    - {u}")
        if len(unique) > 10:
            print(f"    ... und {len(unique) - 10} weitere")

    return result


# ---------------------------------------------------------------------------
# Backup-JSON erstellen
# ---------------------------------------------------------------------------

def build_backup(students_data: list[dict]) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "backup_meta": {
            "version": "1.0",
            "created_at": now,
            "class_id": CLASS_ID,
            "class_name": CLASS_NAME,
            "grade_level": GRADE_LEVEL,
            "competency_list_id": COMPETENCY_LIST_ID,
            "created_by": CREATED_BY,
        },
        "students": students_data,
    }


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> None:
    if not CLASS_ID or not CLASS_NAME:
        sys.exit("Fehler: CLASS_ID und CLASS_NAME müssen im Skript eingetragen werden.")

    # Kompetenzliste laden
    einfach_lookup, niveau_lookup = load_competency_list()

    # Authentifizierung
    token = get_token()

    # Site-ID + Notizbuch
    site_id = get_site_id(token)
    notebook_id, onenote_prefix = find_notebook(token, site_id)
    student_groups = get_student_section_groups(token, notebook_id, onenote_prefix)

    now_iso = datetime.now(timezone.utc).isoformat()
    students_data: list[dict] = []

    for group in student_groups:
        student_name = group.get("displayName", "").strip()
        # System-Abschnitte überspringen (nur die mit "_" am Anfang)
        if student_name.startswith("_"):
            print(f"\nÜberspringe System-Abschnitt: {student_name}")
            continue
        upn = STUDENT_UPN_MAP.get(student_name, "")
        student_id = upn or student_name

        print(f"\nVerarbeite: {student_name} ({upn or '⚠ kein UPN'})")

        student_entry: dict = {
            "student_id": student_id,
            "student_name": student_name,
            "upn": upn,
        }

        # Abschnitte innerhalb der Schüler-Gruppe laden
        group_sections = get_sections_in_group(token, group["id"], onenote_prefix)
        section_by_name = {s.get("displayName", "").strip().lower(): s["id"] for s in group_sections}

        # Seiten liegen im Abschnitt "Kompetenznachweise"
        kompetenzen_section_id = section_by_name.get("kompetenznachweise")
        if not kompetenzen_section_id:
            print(f"  ⚠ Abschnitt 'Kompetenznachweise' nicht gefunden (vorhanden: {list(section_by_name.keys())})")
            students_data.append(student_entry)
            continue

        try:
            # --- Unterrichtskompetenzen (einfach) ---
            ek_page_id = find_page_in_section(token, kompetenzen_section_id, "Unterrichtskompetenzen", onenote_prefix)
            if ek_page_id:
                html = get_page_html(token, ek_page_id, onenote_prefix)
                achieved = parse_einfach_page(html, einfach_lookup)
                if achieved:
                    student_entry["einfach"] = {
                        cid: {"updated_at": now_iso, "updated_by": CREATED_BY}
                        for cid in achieved
                    }
                print(f"  Unterrichtskompetenzen: {len(achieved)} erreicht")
            else:
                print("  ⚠ Seite 'Unterrichtskompetenzen' nicht gefunden")

            # --- Projektkompetenzen (niveau) ---
            pk_page_id = find_page_in_section(token, kompetenzen_section_id, "Projektkompetenzen", onenote_prefix)
            if pk_page_id:
                html = get_page_html(token, pk_page_id, onenote_prefix)
                niveau_results = parse_niveau_page(html, niveau_lookup)
                if niveau_results:
                    student_entry["niveau"] = {}
                    for cid, info in niveau_results.items():
                        entry: dict = {"level": info["level"]}
                        if info.get("url"):
                            entry["nachweise"] = [{
                                "url": info["url"],
                                "name": "Nachweis aus Klassennotizbuch",
                                "updated_at": now_iso,
                            }]
                        student_entry["niveau"][cid] = entry
                print(f"  Projektkompetenzen: {len(niveau_results)} erreicht")
            else:
                print("  ⚠ Seite 'Projektkompetenzen' nicht gefunden")
        except Exception as e:
            print(f"  ✗ Fehler bei Seitenverarbeitung: {e} — überspringe Schüler")

        students_data.append(student_entry)

    # Backup-JSON schreiben
    backup = build_backup(students_data)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_file = f"backup_onenote_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)

    # Zusammenfassung
    total_einfach = sum(len(s.get("einfach", {})) for s in students_data)
    total_niveau = sum(len(s.get("niveau", {})) for s in students_data)
    print(f"\n{'=' * 60}")
    print(f"Backup erstellt: {output_file}")
    print(f"  Schüler:           {len(students_data)}")
    print(f"  Einfach gesamt:    {total_einfach}")
    print(f"  Niveau gesamt:     {total_niveau}")
    print(f"\nNächster Schritt:")
    print(f"  Server: /admin/classes/{CLASS_ID}")
    print(f"  → 'Mitglieder importieren' → JSON-Datei auswählen")
    if any(not s["upn"] for s in students_data):
        missing = [s["student_name"] for s in students_data if not s["upn"]]
        print(f"\n⚠ Kein UPN für: {', '.join(missing)}")
        print("  → Diese Schüler in STUDENT_UPN_MAP nachtragen!")


if __name__ == "__main__":
    main()
