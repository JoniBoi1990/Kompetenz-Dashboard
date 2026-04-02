# Competency Lists — Format Reference

## ID Format Specification

**Format:** `{type}.{grade}{sequence:02d}` — **always strings, never integers**

| Type | Prefix | Example | Meaning |
|------|--------|---------|---------|
| Einfach | `e.` | `e.901` | Klasse 9, Einfach #01 |
| Niveau | `n.` | `n.989` | Klasse 9, Niveau #01 |

**Ranges:**
- Klasse 9 Einfach: `e.901`–`e.988` | Niveau: `n.989`–`n.1021`
- Klasse 10 Einfach: `e.1001`–`e.1070` | Niveau: `n.1071`–`n.1103`

## JSON Entry Structure

```json
{
  "id": "e.901",       // String! Never integer
  "typ": "einfach",    // "einfach" or "niveau" (must match prefix)
  "name": "...",
  "thema": 1,          // Integer 1–10 or null
  "anmerkungen": ""
}
```

## Questions File (`{list}-questions.json`)

```json
{
  "e.901": ["Nenne die Grundbausteine...", "Beschreibe den Aufbau..."],
  "n.989": ["Niveau-Frage..."]
}
```

- Keys = competency IDs as strings with type prefix
- Fallback when key missing: competency name used as single question
- CSV format: Row 0 = IDs as headers (`e.901;e.902;n.989`), rows 1–N = question variants, semikolon-separated UTF-8

## Adding a New Class

**Step 1: Create JSON files**
```bash
python convert_csv_to_json.py --grade 11 --subject chemie \
  --einfach-csv einfach_11.csv --niveau-csv niveau_11.csv \
  --output-dir kompetenzlisten/
```

**Step 2: Add class in web UI**
`Admin → Klassen verwalten → Neue Klasse`

⚠️ **Danach Kompetenzliste zuweisen:** `[Klasse anklicken] → Kompetenzliste zuweisen`
Ohne zugewiesene Liste zeigt Unterrichtsstand 0 Kompetenzen!

**Step 3: Assign students**
`Admin → Klassen verwalten → [Klasse] → Mitglieder`

## Common Pitfalls

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Integer IDs in JSON | Parse errors | Use strings: `"e.1101"` |
| Missing type prefix | ID collisions | Add `e.` or `n.` prefix |
| Wrong sequence padding | `e.111` statt `e.1101` | `e.{grade}{seq:02d}` |
| Missing competency_list_id | Unterrichtsstand 0 Kompetenzen | Im Admin-UI Liste zuweisen |

## Critical Code Paths (sensitive to ID format changes)

| Function | File | Purpose |
|----------|------|---------|
| `_parse_csv_competencies` | `main.py:~815` | CSV → JSON with ID generation |
| `_get_student_competencies` | `main.py:~491` | Loads einfach/niveau lists |
| `teacher_coverage_update` | `main.py:~1345` | Saves active_ids — no `int()` conversion! |
| `get_active_ids` / `set_active_ids` | `db.py:~213/231` | Returns/saves `Set[str]` |

**⚠️ Common bug pattern:**
```python
# WRONG — breaks with string IDs:
ids = {int(v) for k, v in form.multi_items() if k == "active_id"}

# CORRECT:
ids = {v for k, v in form.multi_items() if k == "active_id"}
```

**Templates that handle IDs:**
- `coverage.html` — checkbox values, `k.id in active_ids`
- `test_builder.html` — `parseInt()` removed
- `dashboard.html` — planning mode JSON payloads
- `student_detail.html` — form submissions
