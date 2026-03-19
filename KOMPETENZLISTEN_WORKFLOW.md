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
| 1001 | Die Grundbausteine eines Atoms benennen | einfach | 1 | |
| 1002 | Atome im Schalenmodell darstellen | einfach | 1 | |
| 1003 | Ionenformeln aufstellen | niveau | 2 | z.B. NaCl |

**Wichtige Regeln:**
- **ID-Bereich beachten:**
  - Klasse 9: 901-999
  - Klasse 10: 1001-1099
  - Klasse 11: 1101-1199
- **Typ:** nur `einfach` oder `niveau`
- **Speichern als:** CSV (Semikolon-getrennt, UTF-8)

### 3. Fragen ausfüllen

**Datei: `meine-klasse-10-fragen.csv`**

| competency_id | frage |
|---------------|-------|
| 1001 | Nenne die drei Grundbausteine des Atoms |
| 1001 | Wie ist die Ladung eines Protons? |
| 1002 | Zeichne das Schalenmodell von Sauerstoff |
| 1003 | Stelle die Formel von Natriumchlorid auf |

**Wichtig:**
- `competency_id` muss zur `id` in der Kompetenzen-CSV passen
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
✅ Kompetenzen gespeichert: kompetenzlisten/klasse-10-chemie-klasse-10.json

📁 Lade Fragen aus: meine-klasse-10-fragen.csv
   120 Fragen gefunden
✅ Fragen gespeichert: kompetenzlisten/klasse-10-chemie-klasse-10-questions.json
```

### 5. App neustarten

```bash
# App neustarten damit die neue Liste geladen wird
# Die Listen werden beim Start automatisch in die DB geladen
```

### 6. Im Browser testen

1. Als Lehrer einloggen
2. Klasse 10 auswählen
3. Kompetenzliste "Chemie Klasse 10" zuweisen
4. Test erstellen → Fragen sollten angezeigt werden

---

## Fehlerbehebung

### "ID außerhalb des Bereichs"
→ IDs müssen im richtigen Bereich liegen (z.B. 1001-1099 für Klasse 10)

### "Datei nicht gefunden"
→ Pfad prüfen, Datei muss im Projektordner oder mit vollem Pfad angegeben werden

### "Umlaute werden falsch angezeigt"
→ CSV als UTF-8 speichern (nicht Latin-1 oder Windows-1252)

---

## Migration bestehender Daten

Wenn du bereits eine `kompetenzen.json` hast:

```bash
# Alte IDs (1, 2, 3...) werden zu 901, 902, 903...
python convert_csv_to_json.py \
    --input-kompetenzen _samples/ibK_9_alle.csv \
    --input-fragen _samples/2026-01-30_Testfragen.csv \
    --name "Chemie Klasse 9" \
    --grade 9 \
    --id-offset 900
```

---

## Dateistruktur

```
kompetenzlisten/
├── klasse-9-chemie-klasse-9.json              # Kompetenzen
├── klasse-9-chemie-klasse-9-questions.json    # Fragen
├── klasse-10-chemie-klasse-10.json
└── klasse-10-chemie-klasse-10-questions.json
```

**Namenskonvention:**
- `klasse-{STUFE}-{NAME}.json`
- `klasse-{STUFE}-{NAME}-questions.json`
