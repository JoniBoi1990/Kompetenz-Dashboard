# Workflow: Kompetenzlisten erstellen

## Übersicht

```
Excel/CSV ──► JSON ──► kompetenzlisten/ ──► App lädt automatisch
```

## Schritt-für-Schritt Anleitung

### 1. Vorlagen kopieren

```bash
# Vorlagen aus _samples/ kopieren
cp _samples/vorlage-kompetenzen.csv meine-klasse-10.csv
cp _samples/vorlage-fragen.csv meine-klasse-10-fragen.csv
```

### 2. Kompetenzen ausfüllen (Excel/LibreOffice)

**Datei: `meine-klasse-10.csv`**

| id | name | typ | thema | anmerkungen |
|----|------|-----|-------|-------------|
| e.1001 | Die Grundbausteine eines Atoms benennen | einfach | 1 | |
| e.1002 | Atome im Schalenmodell darstellen | einfach | 1 | |
| n.1071 | Ionenformeln aufstellen | niveau | 2 | z.B. NaCl |

**Wichtige Regeln:**
- **ID-Format mit Typ-Prefix:**
  - Einfache Kompetenzen: `e.{nummer}` (z.B. `e.901`, `e.1001`)
  - Niveau-Kompetenzen: `n.{nummer}` (z.B. `n.989`, `n.1071`)
- **ID-Bereiche:**
  - Klasse 9 einfach: e.901-e.988
  - Klasse 9 niveau: n.989-n.1021
  - Klasse 10 einfach: e.1001-e.1070
  - Klasse 10 niveau: n.1071-n.1103
- **Typ:** nur `einfach` oder `niveau`
- **Speichern als:** CSV (Semikolon-getrennt, UTF-8)

### 3. Fragen ausfüllen

**Datei: `meine-klasse-10-fragen.csv`**

| competency_id | frage |
|---------------|-------|
| e.1001 | Nenne die drei Grundbausteine des Atoms |
| e.1001 | Wie ist die Ladung eines Protons? |
| e.1002 | Zeichne das Schalenmodell von Sauerstoff |
| n.1071 | Stelle die Formel von Natriumchlorid auf |

**Wichtig:**
- `competency_id` muss zur `id` in der Kompetenzen-CSV passen (inkl. Prefix!)
- Mehrere Fragen pro Kompetenz möglich (einfach neue Zeile)

### 4. Konvertieren (JSON erstellen)

```bash
# Mit dem Skript konvertieren
python convert_csv_to_json.py \
    --input-kompetenzen meine-klasse-10.csv \
    --input-fragen meine-klasse-10-fragen.csv \
    --name "Chemie Klasse 10" \
    --grade 10
```

**Ausgabe:**
```
📁 Lade Kompetenzen aus: meine-klasse-10.csv
   50 Kompetenzen gefunden
✅ Kompetenzen gespeichert: kompetenzlisten/klasse-10-chemie.json

📁 Lade Fragen aus: meine-klasse-10-fragen.csv
   120 Fragen gefunden
✅ Fragen gespeichert: kompetenzlisten/klasse-10-chemie-questions.json
```

### 5. App neustarten

```bash
# App neustarten damit die neue Liste geladen wird
# Die Listen werden beim Start automatisch in die DB geladen
```

### 6. Im Browser testen

1. Als Lehrer einloggen
2. Klasse 10 auswählen
3. Kompetenzliste "Chemie Klasse 10" zuweisen (einfach + niveau separat)
4. Test erstellen → Fragen sollten angezeigt werden

---

## Fehlerbehebung

### "ID außerhalb des Bereichs"
→ IDs müssen im richtigen Bereich liegen (z.B. e.1001-e.1070 für Klasse 10 einfach)

### "Datei nicht gefunden"
→ Pfad prüfen, Datei muss im Projektordner oder mit vollem Pfad angegeben werden

### "Umlaute werden falsch angezeigt"
→ CSV als UTF-8 speichern (nicht Latin-1 oder Windows-1252)

---

## Dateistruktur

```
kompetenzlisten/
├── klasse-9-chemie.json              # Kompetenzen
├── klasse-9-chemie-questions.json    # Fragen
├── klasse-10-chemie.json
└── klasse-10-chemie-questions.json
```

**Namenskonvention:**
- `{name}.json` (z.B. `klasse-10-chemie.json`)
- `{name}-questions.json` (z.B. `klasse-10-chemie-questions.json`)
