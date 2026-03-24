"""
Backup/Restore System für Kompetenzstände.

Features:
- JSON-only Format (vereinfacht)
- Nur erreichte Kompetenzen werden gespeichert
- Automatische und manuelle Backups
- Restore mit Merge-Option
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import db

# Backup-Verzeichnisse
BACKUP_DIR = Path(__file__).parent / "_backup"
AUTO_BACKUP_DIR = BACKUP_DIR / "auto"
MANUAL_BACKUP_DIR = BACKUP_DIR / "manual"

# Aufbewahrungsdauer für automatische Backups (Tage)
AUTO_BACKUP_RETENTION_DAYS = 30


def _ensure_backup_dirs():
    """Erstelle Backup-Verzeichnisse falls nicht vorhanden."""
    BACKUP_DIR.mkdir(exist_ok=True)
    AUTO_BACKUP_DIR.mkdir(exist_ok=True)
    MANUAL_BACKUP_DIR.mkdir(exist_ok=True)


def _get_class_backup_dir(class_id: str, manual: bool = False) -> Path:
    """Gibt das Backup-Verzeichnis für eine Klasse zurück."""
    base = MANUAL_BACKUP_DIR if manual else AUTO_BACKUP_DIR
    class_dir = base / class_id
    class_dir.mkdir(exist_ok=True)
    return class_dir


def _generate_backup_filename() -> str:
    """Generiere Backup-Dateiname mit Zeitstempel."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d_%H%M%S.json")


def _sanitize_for_json(obj: Any) -> Any:
    """Entfernt nicht-serialisierbare Werte aus einem Objekt."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    return obj


def create_backup(class_id: str, created_by: str = "system") -> dict:
    """
    Erstelle ein Backup für eine Klasse.
    
    Returns:
        Backup-Daten als Dictionary
    """
    _ensure_backup_dirs()
    
    # Klassen-Info laden
    cls = db.get_class(class_id)
    if not cls:
        raise ValueError(f"Klasse {class_id} nicht gefunden")
    
    # Alle Schüler der Klasse laden
    members = db.get_class_members(class_id)
    
    # Backup-Daten zusammenstellen
    students_data = []
    
    for member in members:
        student_id = member["id"]
        student_name = member["displayName"]
        upn = member.get("userPrincipalName", "")
        
        # Einfach-Records laden (nur erreichte)
        einfach_records = db.get_einfach_records(student_id)
        einfach_achieved = {
            cid: {
                "updated_at": record.get("updated_at", ""),
                "updated_by": record.get("updated_by", ""),
            }
            for cid, record in einfach_records.items()
            if record.get("achieved")
        }
        
        # Niveau-Nachweise laden (nur mit level > 0)
        niveau_nachweise = db.get_nachweise(student_id)
        niveau_data = {}
        
        # Gruppiere Nachweise nach competency_id
        nachweise_by_comp: dict[str, list] = {}
        for nw in niveau_nachweise:
            cid = nw["competency_id"]
            if cid not in nachweise_by_comp:
                nachweise_by_comp[cid] = []
            nachweise_by_comp[cid].append(nw)
        
        for cid, nachweise_list in nachweise_by_comp.items():
            # Höchstes Level finden
            best_nw = max(nachweise_list, key=lambda x: x.get("niveau_level", 0))
            level = best_nw.get("niveau_level", 0)
            
            if level > 0:
                # Nachweise sammeln (ohne interne ID)
                nachweise_clean = [
                    {
                        "url": nw.get("evidence_url", ""),
                        "name": nw.get("evidence_name", ""),
                        "updated_at": nw.get("updated_at", ""),
                    }
                    for nw in nachweise_list
                    if nw.get("evidence_url")  # Nur mit URL
                ]
                
                niveau_data[cid] = {
                    "level": level,
                }
                if nachweise_clean:
                    niveau_data[cid]["nachweise"] = nachweise_clean
        
        # Nur Schüler mit erreichten Kompetenzen aufnehmen
        student_data = {
            "student_id": student_id,
            "student_name": student_name,
            "upn": upn,
        }
        
        if einfach_achieved:
            student_data["einfach"] = einfach_achieved
        if niveau_data:
            student_data["niveau"] = niveau_data
            
        # Schüler auch aufnehmen wenn keine Kompetenzen erreicht
        # (für vollständige Klassenliste)
        students_data.append(student_data)
    
    backup_data = {
        "backup_meta": {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "class_id": class_id,
            "class_name": cls.get("name", ""),
            "grade_level": cls.get("grade_level"),
            "competency_list_id": cls.get("einfach_list_id") or cls.get("competency_list_id"),
            "created_by": created_by,
        },
        "students": students_data,
    }
    
    return backup_data


def save_backup(backup_data: dict, manual: bool = False) -> Path:
    """
    Speichere Backup-Datei.
    
    Returns:
        Pfad zur gespeicherten Datei
    """
    _ensure_backup_dirs()
    
    class_id = backup_data["backup_meta"]["class_id"]
    backup_dir = _get_class_backup_dir(class_id, manual=manual)
    filename = _generate_backup_filename()
    filepath = backup_dir / filename
    
    filepath.write_text(
        json.dumps(backup_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return filepath


def export_backup_json(class_id: str, created_by: str = "system") -> str:
    """
    Exportiere Backup als JSON-String.
    
    Returns:
        JSON-String
    """
    backup_data = create_backup(class_id, created_by)
    return json.dumps(backup_data, ensure_ascii=False, indent=2)


def list_backups(class_id: str | None = None) -> list[dict]:
    """
    Liste alle Backups auf.
    
    Returns:
        Liste von Backup-Metadaten
    """
    _ensure_backup_dirs()
    
    backups = []
    
    def scan_dir(base_dir: Path, is_manual: bool):
        if not base_dir.exists():
            return
        
        for class_dir in base_dir.iterdir():
            if not class_dir.is_dir():
                continue
            
            if class_id and class_dir.name != class_id:
                continue
                
            for backup_file in sorted(class_dir.glob("*.json"), reverse=True):
                try:
                    data = json.loads(backup_file.read_text(encoding="utf-8"))
                    meta = data.get("backup_meta", {})
                    backups.append({
                        "filename": backup_file.name,
                        "class_id": class_dir.name,
                        "class_name": meta.get("class_name", class_dir.name),
                        "created_at": meta.get("created_at", ""),
                        "created_by": meta.get("created_by", "system"),
                        "student_count": len(data.get("students", [])),
                        "filepath": str(backup_file),
                        "is_manual": is_manual,
                        "size_bytes": backup_file.stat().st_size,
                    })
                except Exception:
                    # Ungültige Backup-Datei überspringen
                    continue
    
    scan_dir(AUTO_BACKUP_DIR, is_manual=False)
    scan_dir(MANUAL_BACKUP_DIR, is_manual=True)
    
    # Nach Datum sortieren (neueste zuerst)
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def get_backup(filepath: str) -> dict | None:
    """
    Lade ein bestimmtes Backup.
    
    Returns:
        Backup-Daten oder None
    """
    try:
        path = Path(filepath)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_backup_json(content: str) -> dict:
    """
    Parse Backup-JSON.
    
    Returns:
        Backup-Daten
    
    Raises:
        ValueError: Bei ungültigem Format
    """
    try:
        data = json.loads(content)
        
        # Validierung
        if "backup_meta" not in data:
            raise ValueError("Keine backup_meta gefunden - keine gültige Backup-Datei")
        
        if "students" not in data:
            raise ValueError("Keine students-Daten gefunden")
        
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Ungültiges JSON: {e}")


def is_backup_file(content: str) -> bool:
    """
    Prüfe ob es sich um eine Backup-Datei handelt.
    
    Returns:
        True wenn Backup-Format erkannt
    """
    try:
        data = json.loads(content)
        return "backup_meta" in data and "students" in data
    except Exception:
        return False


def restore_backup(
    class_id: str,
    backup_data: dict,
    merge_mode: bool = True,
    updated_by: str = "system"
) -> dict:
    """
    Stelle ein Backup wieder her.
    
    Args:
        class_id: Ziel-Klasse
        backup_data: Backup-Daten
        merge_mode: True = nur fehlende ergänzen, False = alles überschreiben
        updated_by: Wer führt den Restore durch
    
    Returns:
        Statistik-Daten {"students_added": X, "einfach_restored": Y, "niveau_restored": Z}
    """
    stats = {
        "students_added": 0,
        "einfach_restored": 0,
        "niveau_restored": 0,
        "nachweise_restored": 0,
    }
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Bestehende Schüler der Klasse laden
    existing_members = {m["id"]: m for m in db.get_class_members(class_id)}
    
    for student_data in backup_data.get("students", []):
        student_id = student_data.get("student_id")
        student_name = student_data.get("student_name", "")
        upn = student_data.get("upn", "")
        
        if not student_id:
            continue
        
        # Schüler zur Klasse hinzufügen falls nicht vorhanden
        if student_id not in existing_members:
            db.add_class_member(class_id, student_id, student_name, upn)
            stats["students_added"] += 1
        
        # Einfach-Kompetenzen wiederherstellen
        einfach_data = student_data.get("einfach", {})
        for comp_id, comp_data in einfach_data.items():
            # Im Merge-Modus: Nur wenn noch nicht vorhanden
            if merge_mode:
                existing = db.get_einfach_records(student_id)
                if comp_id in existing and existing[comp_id].get("achieved"):
                    continue
            
            db.upsert_einfach(
                student_id=student_id,
                student_name=student_name,
                competency_id=comp_id,
                achieved=True,
                updated_by=updated_by,
            )
            stats["einfach_restored"] += 1
        
        # Niveau-Kompetenzen wiederherstellen
        niveau_data = student_data.get("niveau", {})
        for comp_id, comp_data in niveau_data.items():
            level = comp_data.get("level", 0)
            if level == 0:
                continue
            
            # Im Merge-Modus: Prüfe ob bereits besseres Level vorhanden
            if merge_mode:
                existing_nachweise = db.get_nachweise(student_id, comp_id)
                if existing_nachweise:
                    best_existing = max(nw.get("niveau_level", 0) for nw in existing_nachweise)
                    if best_existing >= level:
                        continue
            
            # Nachweise wiederherstellen
            nachweise = comp_data.get("nachweise", [])
            
            if nachweise:
                for nw in nachweise:
                    db.add_nachweis(
                        student_id=student_id,
                        student_name=student_name,
                        competency_id=comp_id,
                        niveau_level=level,
                        evidence_url=nw.get("url", ""),
                        evidence_name=nw.get("name", ""),
                        updated_by=updated_by,
                    )
                    stats["nachweise_restored"] += 1
            else:
                # Ohne Nachweis-URL nur das Level speichern
                db.add_nachweis(
                    student_id=student_id,
                    student_name=student_name,
                    competency_id=comp_id,
                    niveau_level=level,
                    evidence_url="",
                    evidence_name="",
                    updated_by=updated_by,
                )
            
            stats["niveau_restored"] += 1
    
    return stats


def cleanup_old_backups() -> int:
    """
    Lösche alte automatische Backups (älter als AUTO_BACKUP_RETENTION_DAYS).
    
    Returns:
        Anzahl gelöschter Dateien
    """
    _ensure_backup_dirs()
    
    cutoff = datetime.now(timezone.utc).timestamp() - (AUTO_BACKUP_RETENTION_DAYS * 86400)
    deleted = 0
    
    for class_dir in AUTO_BACKUP_DIR.iterdir():
        if not class_dir.is_dir():
            continue
        
        for backup_file in class_dir.glob("*.json"):
            try:
                mtime = backup_file.stat().st_mtime
                if mtime < cutoff:
                    backup_file.unlink()
                    deleted += 1
            except Exception:
                continue
        
        # Leere Verzeichnisse entfernen
        try:
            if class_dir.exists() and not any(class_dir.iterdir()):
                class_dir.rmdir()
        except Exception:
            pass
    
    return deleted


def create_automatic_backup(class_id: str) -> Path | None:
    """
    Erstelle ein automatisches Backup für eine Klasse.
    
    Returns:
        Pfad zur Backup-Datei oder None bei Fehler
    """
    try:
        backup_data = create_backup(class_id, created_by="auto")
        return save_backup(backup_data, manual=False)
    except Exception:
        return None


def create_manual_backup(class_id: str, created_by: str) -> Path | None:
    """
    Erstelle ein manuelles Backup für eine Klasse.
    
    Returns:
        Pfad zur Backup-Datei oder None bei Fehler
    """
    try:
        backup_data = create_backup(class_id, created_by=created_by)
        return save_backup(backup_data, manual=True)
    except Exception:
        return None


def delete_backup(filepath: str) -> bool:
    """
    Lösche eine Backup-Datei.
    
    Returns:
        True wenn erfolgreich gelöscht
    """
    try:
        path = Path(filepath)
        if not path.exists():
            return False
        
        # Sicherheitsprüfung: Muss im Backup-Verzeichnis liegen
        if not str(path).startswith(str(BACKUP_DIR)):
            return False
        
        path.unlink()
        
        # Leeres Verzeichnis aufräumen
        try:
            parent = path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass
        
        return True
    except Exception:
        return False
