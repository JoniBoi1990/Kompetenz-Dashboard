"""
Microsoft Graph API client.

All calls are synchronous (httpx) since we use plain FastAPI without async DB.
The access_token comes from the session cookie (delegated auth — acts as the
logged-in user so Graph enforces the user's own permissions).
"""
import httpx
from datetime import datetime, timezone

BASE = "https://graph.microsoft.com/v1.0"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Identity / classes
# ---------------------------------------------------------------------------

def get_my_groups(access_token: str) -> list[dict]:
    """Return all groups the signed-in user is a member of."""
    r = httpx.get(
        f"{BASE}/me/memberOf",
        headers=_headers(access_token),
        params={"$select": "id,displayName,description"},
    )
    r.raise_for_status()
    return r.json().get("value", [])


def get_group_members(access_token: str, group_id: str) -> list[dict]:
    """Return members of a group (teacher: see whole class)."""
    r = httpx.get(
        f"{BASE}/groups/{group_id}/members",
        headers=_headers(access_token),
        params={"$select": "id,displayName,userPrincipalName"},
    )
    r.raise_for_status()
    return r.json().get("value", [])


# ---------------------------------------------------------------------------
# Microsoft Lists (competency records)
# ---------------------------------------------------------------------------

def _list_url(site_id: str, list_id: str) -> str:
    return f"{BASE}/sites/{site_id}/lists/{list_id}"


def get_records(access_token: str, site_id: str, list_id: str,
                student_id: str | None = None) -> list[dict]:
    """
    Read competency records from a Microsoft List.
    Optionally filter by student_id (Azure AD object ID).
    Returns list of { student_id, competency_id, achieved, niveau_level, updated_by, updated_at }.
    """
    url = f"{_list_url(site_id, list_id)}/items"
    params = {
        "$expand": "fields($select=student_id,competency_id,achieved,niveau_level,updated_by,updated_at)",
    }
    if student_id:
        params["$filter"] = f"fields/student_id eq '{student_id}'"

    r = httpx.get(url, headers=_headers(access_token), params=params)
    r.raise_for_status()
    items = r.json().get("value", [])
    return [item["fields"] for item in items]


def upsert_record(
    access_token: str,
    site_id: str,
    list_id: str,
    student_id: str,
    student_name: str,
    competency_id: int,
    achieved: bool | None,
    niveau_level: int | None,
    updated_by: str,
) -> dict:
    """
    Write a competency record.  Checks for an existing item first and
    updates it; otherwise creates a new one.
    Returns the saved fields dict.
    """
    url = f"{_list_url(site_id, list_id)}/items"
    filter_q = (
        f"fields/student_id eq '{student_id}' "
        f"and fields/competency_id eq {competency_id}"
    )
    r = httpx.get(
        url,
        headers=_headers(access_token),
        params={"$filter": filter_q, "$expand": "fields"},
    )
    r.raise_for_status()
    existing = r.json().get("value", [])

    fields = {
        "student_id": student_id,
        "student_name": student_name,
        "competency_id": competency_id,
        "achieved": bool(achieved) if achieved is not None else False,
        "niveau_level": niveau_level or 0,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        item_id = existing[0]["id"]
        r2 = httpx.patch(
            f"{url}/{item_id}",
            headers=_headers(access_token),
            json={"fields": fields},
        )
        r2.raise_for_status()
    else:
        r2 = httpx.post(url, headers=_headers(access_token), json={"fields": fields})
        r2.raise_for_status()

    return fields


def ensure_nachweise_list(access_token: str, site_id: str) -> str:
    """Return (creating if needed) the ID of the 'Nachweise' list."""
    list_name = "Nachweise"
    r = httpx.get(
        f"{BASE}/sites/{site_id}/lists",
        headers=_headers(access_token),
        params={"$filter": f"displayName eq '{list_name}'", "$select": "id,displayName"},
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    if items:
        return items[0]["id"]

    body = {
        "displayName": list_name,
        "columns": [
            {"name": "student_id", "text": {}},
            {"name": "student_name", "text": {}},
            {"name": "competency_id", "number": {}},
            {"name": "niveau_level", "number": {}},
            {"name": "evidence_url", "text": {}},
            {"name": "evidence_name", "text": {}},
            {"name": "updated_by", "text": {}},
            {"name": "updated_at", "dateTime": {"format": "dateTime"}},
        ],
        "list": {"template": "genericList"},
    }
    r2 = httpx.post(f"{BASE}/sites/{site_id}/lists", headers=_headers(access_token), json=body)
    r2.raise_for_status()
    return r2.json()["id"]


def get_nachweise(
    access_token: str,
    site_id: str,
    list_id: str,
    student_id: str,
    competency_id: int | None = None,
) -> list[dict]:
    """Return all evidence entries for a student, optionally filtered by competency."""
    url = f"{_list_url(site_id, list_id)}/items"
    filter_q = f"fields/student_id eq '{student_id}'"
    if competency_id is not None:
        filter_q += f" and fields/competency_id eq {competency_id}"

    r = httpx.get(
        url,
        headers=_headers(access_token),
        params={
            "$filter": filter_q,
            "$expand": "fields($select=student_id,student_name,competency_id,niveau_level,"
                       "evidence_url,evidence_name,updated_by,updated_at)",
        },
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    fields_list = [item["fields"] for item in items]
    # Normalize competency_id to int and sort newest-first
    for f in fields_list:
        f["competency_id"] = int(f.get("competency_id", 0))
        f["niveau_level"] = int(f.get("niveau_level", 0))
    fields_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return fields_list


def add_nachweis(
    access_token: str,
    site_id: str,
    list_id: str,
    student_id: str,
    student_name: str,
    competency_id: int,
    niveau_level: int,
    evidence_url: str,
    evidence_name: str,
    updated_by: str,
) -> dict:
    """Append a new evidence entry (never overwrites — multiple entries allowed)."""
    fields = {
        "student_id": student_id,
        "student_name": student_name,
        "competency_id": competency_id,
        "niveau_level": niveau_level,
        "evidence_url": evidence_url,
        "evidence_name": evidence_name or evidence_url,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = httpx.post(
        f"{_list_url(site_id, list_id)}/items",
        headers=_headers(access_token),
        json={"fields": fields},
    )
    r.raise_for_status()
    return fields


# ---------------------------------------------------------------------------
# Active competencies (which ones have been covered in class)
# ---------------------------------------------------------------------------

_SETTINGS_LIST = "Einstellungen"


def get_active_competency_ids(access_token: str, site_id: str) -> set[int]:
    """Return set of competency IDs marked as covered in class."""
    try:
        r = httpx.get(
            f"{BASE}/sites/{site_id}/lists",
            headers=_headers(access_token),
            params={"$filter": f"displayName eq '{_SETTINGS_LIST}'", "$select": "id"},
        )
        r.raise_for_status()
        lists = r.json().get("value", [])
        if not lists:
            return set()
        list_id = lists[0]["id"]
        r2 = httpx.get(
            f"{BASE}/sites/{site_id}/lists/{list_id}/items",
            headers=_headers(access_token),
            params={
                "$filter": "fields/key eq 'active_competencies'",
                "$expand": "fields($select=key,value)",
            },
        )
        r2.raise_for_status()
        items = r2.json().get("value", [])
        if not items:
            return set()
        val = items[0]["fields"].get("value", "")
        return {int(x) for x in val.split(",") if x.strip().isdigit()}
    except Exception:
        return set()


def set_active_competency_ids(access_token: str, site_id: str, ids: set[int]) -> None:
    """Save active competency IDs to SharePoint settings list."""
    val = ",".join(str(i) for i in sorted(ids))
    # Ensure list exists
    r = httpx.get(
        f"{BASE}/sites/{site_id}/lists",
        headers=_headers(access_token),
        params={"$filter": f"displayName eq '{_SETTINGS_LIST}'", "$select": "id"},
    )
    r.raise_for_status()
    lists = r.json().get("value", [])
    if lists:
        list_id = lists[0]["id"]
    else:
        r2 = httpx.post(
            f"{BASE}/sites/{site_id}/lists",
            headers=_headers(access_token),
            json={
                "displayName": _SETTINGS_LIST,
                "columns": [{"name": "key", "text": {}}, {"name": "value", "text": {}}],
                "list": {"template": "genericList"},
            },
        )
        r2.raise_for_status()
        list_id = r2.json()["id"]

    items_url = f"{BASE}/sites/{site_id}/lists/{list_id}/items"
    r3 = httpx.get(
        items_url,
        headers=_headers(access_token),
        params={"$filter": "fields/key eq 'active_competencies'", "$expand": "fields"},
    )
    r3.raise_for_status()
    existing = r3.json().get("value", [])
    if existing:
        httpx.patch(
            f"{items_url}/{existing[0]['id']}",
            headers=_headers(access_token),
            json={"fields": {"value": val}},
        ).raise_for_status()
    else:
        httpx.post(
            items_url,
            headers=_headers(access_token),
            json={"fields": {"key": "active_competencies", "value": val}},
        ).raise_for_status()


def ensure_list_exists(access_token: str, site_id: str, list_name: str) -> str:
    """
    Return the list ID for `list_name` on the given site.
    Creates the list (with the required columns) if it doesn't exist yet.
    """
    r = httpx.get(
        f"{BASE}/sites/{site_id}/lists",
        headers=_headers(access_token),
        params={"$filter": f"displayName eq '{list_name}'", "$select": "id,displayName"},
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    if items:
        return items[0]["id"]

    # Create list
    body = {
        "displayName": list_name,
        "columns": [
            {"name": "student_id", "text": {}},
            {"name": "student_name", "text": {}},
            {"name": "competency_id", "number": {}},
            {"name": "achieved", "boolean": {}},
            {"name": "niveau_level", "number": {}},
            {"name": "updated_by", "text": {}},
            {"name": "updated_at", "dateTime": {"format": "dateTime"}},
        ],
        "list": {"template": "genericList"},
    }
    r2 = httpx.post(
        f"{BASE}/sites/{site_id}/lists",
        headers=_headers(access_token),
        json=body,
    )
    r2.raise_for_status()
    return r2.json()["id"]


# ---------------------------------------------------------------------------
# Kompetenzanträge (production stubs — parallel to nachweis helpers)
# ---------------------------------------------------------------------------

def ensure_kompetenzantraege_list(access_token: str, site_id: str) -> str:
    """Return list ID for 'Kompetenzantraege', creating it if absent."""
    r = httpx.get(
        f"{BASE}/sites/{site_id}/lists",
        headers=_headers(access_token),
        params={"$filter": "displayName eq 'Kompetenzantraege'", "$select": "id"},
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    if items:
        return items[0]["id"]

    body = {
        "displayName": "Kompetenzantraege",
        "columns": [
            {"name": "antrag_id", "text": {}},
            {"name": "student_id", "text": {}},
            {"name": "student_name", "text": {}},
            {"name": "competency_id", "number": {}},
            {"name": "typ", "text": {}},
            {"name": "beschreibung", "text": {}},
            {"name": "evidence_url", "text": {}},
            {"name": "created_at", "dateTime": {"format": "dateTime"}},
            {"name": "status", "text": {}},
            {"name": "begruendung", "text": {}},
            {"name": "niveau_level", "number": {}},
        ],
        "list": {"template": "genericList"},
    }
    r2 = httpx.post(f"{BASE}/sites/{site_id}/lists", headers=_headers(access_token), json=body)
    r2.raise_for_status()
    return r2.json()["id"]


def add_kompetenzantrag(access_token: str, site_id: str, list_id: str, antrag: dict) -> None:
    """POST a new Kompetenzantrag item to the SharePoint list."""
    r = httpx.post(
        f"{_list_url(site_id, list_id)}/items",
        headers=_headers(access_token),
        json={"fields": antrag},
    )
    r.raise_for_status()


def get_kompetenzantraege(
    access_token: str,
    site_id: str,
    list_id: str,
    student_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """GET Kompetenzantrag items, optionally filtered by student_id or status."""
    params: dict = {"$expand": "fields"}
    filters = []
    if student_id:
        filters.append(f"fields/student_id eq '{student_id}'")
    if status:
        filters.append(f"fields/status eq '{status}'")
    if filters:
        params["$filter"] = " and ".join(filters)
    r = httpx.get(
        f"{_list_url(site_id, list_id)}/items",
        headers=_headers(access_token),
        params=params,
    )
    r.raise_for_status()
    return [item["fields"] for item in r.json().get("value", [])]


def update_kompetenzantrag(
    access_token: str,
    site_id: str,
    list_id: str,
    item_id: str,
    **fields,
) -> None:
    """PATCH a Kompetenzantrag item (e.g. update status, begruendung, niveau_level)."""
    r = httpx.patch(
        f"{_list_url(site_id, list_id)}/items/{item_id}",
        headers=_headers(access_token),
        json={"fields": fields},
    )
    r.raise_for_status()
