"""
OneNote Sync Service für automatische Synchronisierung von Klassennotizbüchern.

Basierend auf onenote_to_backup.py, aber modularisiert für Server-Betrieb.
"""

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

import db

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Notes.Read.All"]

NIVEAU_LABELS = {
    "experte": 3,
    "expert": 3,
    "advanced": 2,
    "fortgeschritten": 2,
    "beginner": 1,
    "anfänger": 1,
    "anfaenger": 1,
}


class OneNoteSyncError(Exception):
    """Base exception for OneNote sync errors."""
    pass


class OneNoteAuthError(OneNoteSyncError):
    """Authentication failed."""
    pass


class OneNoteNotFoundError(OneNoteSyncError):
    """Notebook or page not found."""
    pass


class OneNoteSyncService:
    """Service for syncing OneNote class notebooks with the dashboard."""
    
    def __init__(self, access_token: str):
        self.token = access_token
        self.stats = {
            "students_processed": 0,
            "einfach_added": 0,
            "niveau_added": 0,
            "details": {},
        }
    
    def _graph_get(self, path: str, **params) -> dict:
        """Make a GET request to Graph API with retry logic."""
        url = path if path.startswith("https://") else f"{GRAPH_BASE}{path}"
        
        for attempt in range(4):
            try:
                r = httpx.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=params or None,
                    timeout=30,
                )
                
                if r.status_code == 401:
                    raise OneNoteAuthError("Token ungültig oder abgelaufen")
                
                if r.status_code in (429, 500, 502, 503, 504):
                    wait = int(r.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(wait)
                    continue
                
                r.raise_for_status()
                return r.json()
            
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise OneNoteSyncError(f"Graph API Fehler: {e}")
                time.sleep(2 ** attempt)
        
        return {}
    
    def _get_page_html(self, page_id: str, onenote_prefix: str) -> str:
        """Get HTML content of a OneNote page."""
        url = f"{GRAPH_BASE}{onenote_prefix}/pages/{page_id}/content"
        
        try:
            r = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
                follow_redirects=True,
            )
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as e:
            raise OneNoteSyncError(f"Fehler beim Laden der Seite: {e}")
    
    def _get_site_id(self, site_url: str) -> str:
        """Get SharePoint site ID from URL."""
        url = site_url.rstrip("/")
        match = re.match(r"https://([^/]+)(/.+)", url)
        
        if not match:
            raise OneNoteSyncError(f"Ungültige Site-URL: {site_url}")
        
        host, path = match.group(1), match.group(2)
        data = self._graph_get(f"/sites/{host}:{path}")
        site_id = data.get("id", "")
        
        if not site_id:
            raise OneNoteNotFoundError(f"Site-ID konnte nicht ermittelt werden für: {site_url}")
        
        return site_id
    
    def _find_notebook(self, site_id: str, notebook_name: str) -> tuple[str, str]:
        """Find notebook and return (notebook_id, prefix)."""
        candidates = [
            ("/me/onenote/notebooks", "/me/onenote"),
            (f"/sites/{site_id}/onenote/notebooks", f"/sites/{site_id}/onenote"),
        ]
        
        all_names = []
        
        for list_endpoint, prefix in candidates:
            try:
                data = self._graph_get(list_endpoint)
                notebooks = data.get("value", [])
                
                for nb in notebooks:
                    name = nb.get("displayName", "").strip()
                    all_names.append(name)
                    
                    if name == notebook_name.strip():
                        return nb["id"], prefix
            except Exception:
                continue
        
        raise OneNoteNotFoundError(
            f"Notizbuch '{notebook_name}' nicht gefunden. "
            f"Verfügbare: {', '.join(all_names)}"
        )
    
    def _get_student_sections(self, notebook_id: str, onenote_prefix: str) -> list[dict]:
        """Get all student section groups from notebook."""
        data = self._graph_get(f"{onenote_prefix}/notebooks/{notebook_id}/sectionGroups")
        groups = data.get("value", [])
        
        if groups:
            return groups
        
        # Fallback: direct sections
        data = self._graph_get(f"{onenote_prefix}/notebooks/{notebook_id}/sections")
        return data.get("value", [])
    
    def _get_sections_in_group(self, group_id: str, onenote_prefix: str) -> list[dict]:
        """Get sections within a student section group."""
        data = self._graph_get(f"{onenote_prefix}/sectionGroups/{group_id}/sections")
        return data.get("value", [])
    
    def _find_page_in_section(self, section_id: str, page_title: str, onenote_prefix: str) -> str | None:
        """Find page by title in a section."""
        data = self._graph_get(f"{onenote_prefix}/sections/{section_id}/pages")
        pages = data.get("value", [])
        
        for p in pages:
            if p.get("title", "").strip().lower() == page_title.strip().lower():
                return p["id"]
        
        return None
    
    def _normalize(self, text: str) -> str:
        """Normalize text for matching."""
        return " ".join(text.lower().strip().split())
    
    def _match_competency(self, text: str, lookup: dict[str, dict]) -> dict | None:
        """Match competency by text using various strategies."""
        key = self._normalize(text)
        
        # 1. Exact match
        if key in lookup:
            return lookup[key]
        
        # 2. Substring match
        for k, comp in lookup.items():
            if key in k or k in key:
                return comp
        
        # 3. Word overlap (≥60%)
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
    
    def _parse_einfach_page(self, html: str, einfach_lookup: dict[str, dict]) -> dict[str, bool]:
        """Parse 'Unterrichtskompetenzen' page and return achieved competencies."""
        soup = BeautifulSoup(html, "html.parser")
        achieved = {}
        unmatched = []
        
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            
            # Find competency column
            header_cells = rows[0].find_all(["th", "td"])
            text_col = None
            
            for i, cell in enumerate(header_cells):
                h = self._normalize(cell.get_text(strip=True))
                if "kompetenz" in h:
                    text_col = i
                    break
            
            if text_col is None:
                continue
            
            # Process data rows
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                if len(cells) <= text_col:
                    continue
                
                comp_text = re.sub(r"\s+", " ", cells[text_col].get_text(strip=True)).strip()
                if not comp_text:
                    continue
                
                # Find checkbox
                checkbox = cells[-1].find("input", {"type": "checkbox"})
                if checkbox is None:
                    checkbox = row.find("input", {"type": "checkbox"})
                
                is_checked = checkbox is not None and checkbox.has_attr("checked")
                
                comp = self._match_competency(comp_text, einfach_lookup)
                if comp:
                    if is_checked:
                        achieved[comp["id"]] = True
                elif is_checked:
                    unmatched.append(comp_text)
        
        return achieved, unmatched
    
    def _parse_niveau_page(self, html: str, niveau_lookup: dict[str, dict]) -> dict[str, dict]:
        """Parse 'Projektkompetenzen' page and return niveau achievements."""
        soup = BeautifulSoup(html, "html.parser")
        result = {}
        unmatched = []
        
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            
            # Parse header
            header_cells = rows[0].find_all(["th", "td"])
            col_to_level = {}
            text_col = None
            
            for i, cell in enumerate(header_cells):
                header_text = self._normalize(cell.get_text(strip=True))
                
                if header_text in NIVEAU_LABELS:
                    col_to_level[i] = NIVEAU_LABELS[header_text]
                elif header_text in ("pbk", "kompetenz", "projektbasierte kompetenz") or (
                    "kompetenz" in header_text and text_col is None
                ):
                    text_col = i
            
            if not col_to_level:
                continue
            
            # Fallback for text column
            if text_col is None:
                first_niveau_col = min(col_to_level.keys())
                text_col = max(0, first_niveau_col - 1)
                if text_col == 0 and first_niveau_col > 1:
                    text_col = 1
            
            # Process data rows
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                if not cells or len(cells) <= text_col:
                    continue
                
                comp_name = cells[text_col].get_text(separator=" ", strip=True)
                comp_name = re.sub(r"\s+", " ", comp_name).strip()
                
                if not comp_name:
                    continue
                
                comp = self._match_competency(comp_name, niveau_lookup)
                if not comp:
                    unmatched.append(comp_name)
                    continue
                
                # Find best level
                best_level = 0
                best_url = None
                
                for col_idx, level in col_to_level.items():
                    if col_idx >= len(cells):
                        continue
                    
                    cell = cells[col_idx]
                    cell_text = cell.get_text(separator=" ", strip=True)
                    link = cell.find("a")
                    url = link["href"] if link and link.has_attr("href") else None
                    
                    if cell_text or url:
                        if level > best_level:
                            best_level = level
                            best_url = url or cell_text or None
                
                if best_level > 0:
                    result[comp["id"]] = {"level": best_level, "url": best_url}
        
        return result, unmatched
    
    def _load_competency_lists(self, class_id: str) -> tuple[dict[str, dict], dict[str, dict]]:
        """Load competency lists for a class and build lookup dictionaries."""
        from pathlib import Path
        
        cls = db.get_class(class_id)
        if not cls:
            raise OneNoteSyncError(f"Klasse {class_id} nicht gefunden")
        
        einfach_lookup = {}
        niveau_lookup = {}
        
        # Base directory for competency lists
        base_dir = Path(__file__).parent
        
        # Load einfach list
        einfach_list_id = cls.get("einfach_list_id") or cls.get("competency_list_id")
        if einfach_list_id:
            try:
                # Try system list first
                list_file = base_dir / "kompetenzlisten" / f"{einfach_list_id}.json"
                
                if list_file.exists():
                    data = json.loads(list_file.read_text(encoding="utf-8"))
                    for c in data.get("competencies", []):
                        if c.get("typ") in ("einfach", None):
                            einfach_lookup[self._normalize(c["name"])] = c
                else:
                    # Try teacher list
                    teacher_list = db.get_teacher_list(einfach_list_id)
                    if teacher_list:
                        for c in teacher_list["data"].get("competencies", []):
                            if c.get("typ") in ("einfach", None):
                                einfach_lookup[self._normalize(c["name"])] = c
            except Exception as e:
                raise OneNoteSyncError(f"Fehler beim Laden der Einfach-Liste: {e}")
        
        # Load niveau list
        niveau_list_id = cls.get("niveau_list_id") or cls.get("competency_list_id")
        if niveau_list_id:
            try:
                list_file = base_dir / "kompetenzlisten" / f"{niveau_list_id}.json"
                
                if list_file.exists():
                    data = json.loads(list_file.read_text(encoding="utf-8"))
                    for c in data.get("competencies", []):
                        if c.get("typ") == "niveau":
                            niveau_lookup[self._normalize(c["name"])] = c
                else:
                    teacher_list = db.get_teacher_list(niveau_list_id)
                    if teacher_list:
                        for c in teacher_list["data"].get("competencies", []):
                            if c.get("typ") == "niveau":
                                niveau_lookup[self._normalize(c["name"])] = c
            except Exception as e:
                raise OneNoteSyncError(f"Fehler beim Laden der Niveau-Liste: {e}")
        
        return einfach_lookup, niveau_lookup
    
    def _merge_student_data(
        self,
        class_id: str,
        student_data: list[dict],
        updated_by: str,
    ) -> dict:
        """Merge student data into dashboard. Returns statistics."""
        now = datetime.now(timezone.utc).isoformat()
        details = {}
        
        einfach_count = 0
        niveau_count = 0
        
        for student in student_data:
            student_id = student["student_id"]
            student_name = student["student_name"]
            student_details = {"einfach": [], "niveau": []}
            
            # Merge einfach competencies
            einfach_data = student.get("einfach", {})
            if einfach_data:
                existing = db.get_einfach_records(student_id)
                
                for comp_id in einfach_data:
                    # Only add if not already achieved
                    if comp_id not in existing or not existing[comp_id].get("achieved"):
                        db.upsert_einfach(
                            student_id=student_id,
                            student_name=student_name,
                            competency_id=comp_id,
                            achieved=True,
                            updated_by=updated_by,
                        )
                        einfach_count += 1
                        student_details["einfach"].append(comp_id)
            
            # Merge niveau competencies (add new nachweis, never overwrite)
            niveau_data = student.get("niveau", {})
            if niveau_data:
                for comp_id, comp_info in niveau_data.items():
                    level = comp_info.get("level", 0)
                    url = comp_info.get("url", "")
                    
                    if level == 0:
                        continue
                    
                    # Always add as new nachweis (appends to history)
                    db.add_nachweis(
                        student_id=student_id,
                        student_name=student_name,
                        competency_id=comp_id,
                        niveau_level=level,
                        evidence_url=url,
                        evidence_name=url or f"OneNote Sync ({level})",
                        updated_by=updated_by,
                    )
                    niveau_count += 1
                    student_details["niveau"].append({"id": comp_id, "level": level})
            
            if student_details["einfach"] or student_details["niveau"]:
                details[student_id] = {
                    "name": student_name,
                    "added": student_details,
                }
        
        return {
            "einfach_added": einfach_count,
            "niveau_added": niveau_count,
            "details": details,
        }
    
    async def sync_class(
        self,
        class_id: str,
        config: dict,
        triggered_by: str = "auto",
    ) -> dict:
        """
        Sync a class from OneNote.
        
        Args:
            class_id: The class ID to sync
            config: Sync configuration dict with keys:
                - site_url: SharePoint site URL
                - notebook_name: Name of the notebook
                - section_name: Section name (default: "Kompetenznachweise")
                - student_mapping: Dict mapping OneNote names to UPNs
            triggered_by: Who triggered the sync ('auto', 'manual', or username)
        
        Returns:
            Dict with sync results
        """
        self.stats = {
            "students_processed": 0,
            "einfach_added": 0,
            "niveau_added": 0,
            "details": {},
        }
        
        site_url = config["site_url"]
        notebook_name = config["notebook_name"]
        section_name = config.get("section_name", "Kompetenznachweise")
        student_mapping = config.get("student_mapping", {})
        
        try:
            # Load competency lists
            einfach_lookup, niveau_lookup = self._load_competency_lists(class_id)
            
            if not einfach_lookup and not niveau_lookup:
                raise OneNoteSyncError("Keine Kompetenzlisten für diese Klasse gefunden")
            
            # Get site and notebook
            site_id = self._get_site_id(site_url)
            notebook_id, onenote_prefix = self._find_notebook(site_id, notebook_name)
            
            # Get student sections
            student_groups = self._get_student_sections(notebook_id, onenote_prefix)
            
            students_data = []
            now_iso = datetime.now(timezone.utc).isoformat()
            
            for group in student_groups:
                student_name = group.get("displayName", "").strip()
                
                # Skip system sections
                if student_name.startswith("_"):
                    continue
                
                # Map to UPN
                upn = student_mapping.get(student_name, "")
                if not upn:
                    # Try to find matching class member by name similarity
                    members = db.get_class_members(class_id)
                    for m in members:
                        if self._normalize(m["displayName"]) == self._normalize(student_name):
                            upn = m.get("userPrincipalName", m["id"])
                            break
                
                student_id = upn or student_name
                
                student_entry = {
                    "student_id": student_id,
                    "student_name": student_name,
                    "upn": upn,
                }
                
                # Get sections in group
                group_sections = self._get_sections_in_group(group["id"], onenote_prefix)
                section_by_name = {
                    s.get("displayName", "").strip().lower(): s["id"]
                    for s in group_sections
                }
                
                kompetenzen_section_id = section_by_name.get(section_name.lower())
                if not kompetenzen_section_id:
                    students_data.append(student_entry)
                    continue
                
                try:
                    # Parse Unterrichtskompetenzen
                    ek_page_id = self._find_page_in_section(
                        kompetenzen_section_id, "Unterrichtskompetenzen", onenote_prefix
                    )
                    if ek_page_id and einfach_lookup:
                        html = self._get_page_html(ek_page_id, onenote_prefix)
                        achieved, _ = self._parse_einfach_page(html, einfach_lookup)
                        if achieved:
                            student_entry["einfach"] = achieved
                    
                    # Parse Projektkompetenzen
                    pk_page_id = self._find_page_in_section(
                        kompetenzen_section_id, "Projektkompetenzen", onenote_prefix
                    )
                    if pk_page_id and niveau_lookup:
                        html = self._get_page_html(pk_page_id, onenote_prefix)
                        niveau_results, _ = self._parse_niveau_page(html, niveau_lookup)
                        if niveau_results:
                            student_entry["niveau"] = niveau_results
                
                except Exception as e:
                    # Log but continue with other students
                    print(f"Fehler bei Schüler {student_name}: {e}")
                
                students_data.append(student_entry)
                self.stats["students_processed"] += 1
            
            # Merge into dashboard
            merge_result = self._merge_student_data(
                class_id=class_id,
                student_data=students_data,
                updated_by=f"onenote_sync ({triggered_by})",
            )
            
            self.stats["einfach_added"] = merge_result["einfach_added"]
            self.stats["niveau_added"] = merge_result["niveau_added"]
            self.stats["details"] = merge_result["details"]
            
            return {
                "status": "success",
                "students_processed": self.stats["students_processed"],
                "einfach_added": self.stats["einfach_added"],
                "niveau_added": self.stats["niveau_added"],
                "details": self.stats["details"],
            }
        
        except OneNoteAuthError as e:
            return {"status": "error", "error": f"Authentifizierungsfehler: {e}"}
        except OneNoteNotFoundError as e:
            return {"status": "error", "error": f"Nicht gefunden: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Unerwarteter Fehler: {e}"}


async def run_sync_for_class(
    class_id: str,
    access_token: str,
    triggered_by: str = "auto",
) -> dict:
    """
    Run a complete sync for a class including history tracking.
    
    This is the main entry point for sync operations.
    """
    # Get config
    config = db.get_onenote_sync_config(class_id)
    if not config:
        return {"status": "error", "error": "Keine OneNote-Konfiguration für diese Klasse"}
    
    if not config["enabled"]:
        return {"status": "error", "error": "OneNote-Sync ist deaktiviert"}
    
    # Create history entry
    history_id = db.create_sync_history(class_id, triggered_by)
    
    try:
        # Run sync
        service = OneNoteSyncService(access_token)
        result = await service.sync_class(class_id, config, triggered_by)
        
        # Update history
        if result["status"] == "success":
            db.finish_sync_history(
                history_id=history_id,
                status="success",
                students_processed=result["students_processed"],
                einfach_added=result["einfach_added"],
                niveau_added=result["niveau_added"],
                details=result["details"],
            )
            db.update_onenote_sync_status(class_id, "success")
        else:
            db.finish_sync_history(
                history_id=history_id,
                status="error",
                error_message=result.get("error", "Unbekannter Fehler"),
            )
            db.update_onenote_sync_status(
                class_id, "error", result.get("error", "Unbekannter Fehler")
            )
        
        return result
    
    except Exception as e:
        db.finish_sync_history(
            history_id=history_id,
            status="error",
            error_message=str(e),
        )
        db.update_onenote_sync_status(class_id, "error", str(e))
        return {"status": "error", "error": str(e)}


async def run_all_enabled_syncs(access_token: str) -> list[dict]:
    """Run sync for all enabled classes. Returns list of results."""
    configs = db.get_enabled_onenote_sync_configs()
    results = []
    
    for config in configs:
        result = await run_sync_for_class(
            config["class_id"],
            access_token,
            triggered_by="auto",
        )
        results.append({
            "class_id": config["class_id"],
            **result,
        })
    
    return results
