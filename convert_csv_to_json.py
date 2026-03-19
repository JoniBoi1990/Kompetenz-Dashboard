#!/usr/bin/env python3
"""
Konvertiert CSV-Dateien zu kompetenzlisten/ JSON-Format

Verwendung:
    python convert_csv_to_json.py \
        --input-kompetenzen _samples/klasse-10-chemie.csv \
        --input-fragen _samples/klasse-10-chemie-fragen.csv \
        --output-dir kompetenzlisten/ \
        --name "Chemie Klasse 10" \
        --grade 10
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def load_csv(filepath: str) -> list[dict]:
    """Lädt CSV mit korrekter Encoding-Erkennung"""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ Datei nicht gefunden: {filepath}")
        sys.exit(1)
    
    # Versuche UTF-8 mit BOM
    try:
        with open(path, encoding='utf-8-sig') as f:
            return list(csv.DictReader(f, delimiter=';'))
    except UnicodeDecodeError:
        pass
    
    # Fallback: UTF-8 ohne BOM
    try:
        with open(path, encoding='utf-8') as f:
            return list(csv.DictReader(f, delimiter=';'))
    except UnicodeDecodeError:
        pass
    
    # Fallback: Latin-1
    with open(path, encoding='latin-1') as f:
        return list(csv.DictReader(f, delimiter=';'))


def validate_ids(competencies: list[dict], grade_level: int):
    """Prüft ob IDs im richtigen Bereich liegen"""
    expected_prefix = grade_level * 100  # 9*100=900, 10*100=1000
    
    errors = []
    for comp in competencies:
        comp_id = int(comp.get('id', 0))
        if not (expected_prefix <= comp_id < expected_prefix + 100):
            errors.append(f"  ID {comp_id} ist außerhalb des Bereichs {expected_prefix}-{expected_prefix+99}")
    
    if errors:
        print(f"❌ ID-Validierungsfehler:")
        for e in errors:
            print(e)
        print(f"\n💡 Tipp: IDs für Klasse {grade_level} sollten zwischen {expected_prefix} und {expected_prefix+99} liegen")
        return False
    
    return True


def convert_kompetenzen(csv_data: list[dict]) -> list[dict]:
    """Konvertiert CSV-Zeilen zu Kompetenz-Objekten"""
    result = []
    for row in csv_data:
        comp = {
            "id": int(row.get('id', 0)),
            "name": row.get('name', '').strip(),
            "typ": row.get('typ', 'einfach').strip().lower(),
            "thema": int(row.get('thema', 0)) if row.get('thema') else None,
        }
        if row.get('anmerkungen'):
            comp['anmerkungen'] = row['anmerkungen'].strip()
        result.append(comp)
    return result


def convert_fragen(csv_data: list[dict]) -> dict:
    """Gruppiert Fragen nach competency_id"""
    result = {}
    for row in csv_data:
        comp_id = row.get('competency_id', '').strip()
        frage = row.get('frage', '').strip()
        if comp_id and frage:
            if comp_id not in result:
                result[comp_id] = []
            result[comp_id].append(frage)
    return result


def main():
    parser = argparse.ArgumentParser(description='CSV zu JSON Konverter für Kompetenzlisten')
    parser.add_argument('--input-kompetenzen', required=True, help='CSV-Datei mit Kompetenzen')
    parser.add_argument('--input-fragen', help='CSV-Datei mit Fragen (optional)')
    parser.add_argument('--output-dir', default='kompetenzlisten/', help='Ausgabeverzeichnis')
    parser.add_argument('--name', required=True, help='Name der Kompetenzliste')
    parser.add_argument('--grade', type=int, required=True, help='Klassenstufe (z.B. 9, 10)')
    parser.add_argument('--id-offset', type=int, default=0, help='Zu allen IDs addieren (für Migration)')
    
    args = parser.parse_args()
    
    print(f"📁 Lade Kompetenzen aus: {args.input_kompetenzen}")
    comp_csv = load_csv(args.input_kompetenzen)
    print(f"   {len(comp_csv)} Kompetenzen gefunden")
    
    # IDs anpassen falls Offset angegeben
    if args.id_offset:
        for row in comp_csv:
            row['id'] = int(row.get('id', 0)) + args.id_offset
    
    # Validierung
    if not validate_ids(comp_csv, args.grade):
        sys.exit(1)
    
    # Konvertieren
    competencies = convert_kompetenzen(comp_csv)
    
    # Ausgabedatei bestimmen
    safe_name = args.name.lower().replace(' ', '-').replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Kompetenzen speichern
    output_file = output_dir / f"klasse-{args.grade}-{safe_name}.json"
    output_data = {
        "name": args.name,
        "grade_level": args.grade,
        "description": f"Kompetenzliste für {args.name} Klasse {args.grade}",
        "competencies": competencies
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Kompetenzen gespeichert: {output_file}")
    
    # Fragen verarbeiten
    if args.input_fragen:
        print(f"\n📁 Lade Fragen aus: {args.input_fragen}")
        fragen_csv = load_csv(args.input_fragen)
        print(f"   {len(fragen_csv)} Fragen gefunden")
        
        questions = convert_fragen(fragen_csv)
        
        # IDs in Fragen auch anpassen falls Offset
        if args.id_offset:
            new_questions = {}
            for k, v in questions.items():
                new_key = str(int(k) + args.id_offset)
                new_questions[new_key] = v
            questions = new_questions
        
        fragen_file = output_dir / f"klasse-{args.grade}-{safe_name}-questions.json"
        with open(fragen_file, 'w', encoding='utf-8') as f:
            json.dump(questions, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Fragen gespeichert: {fragen_file}")
    
    print(f"\n📊 Zusammenfassung:")
    print(f"   Klassenstufe: {args.grade}")
    print(f"   Name: {args.name}")
    print(f"   Kompetenzen: {len(competencies)}")
    if args.input_fragen:
        print(f"   Fragen: {sum(len(v) for v in questions.values())} (für {len(questions)} Kompetenzen)")
    print(f"\n💡 Nächster Schritt: App neustarten um die neue Liste zu laden")


if __name__ == "__main__":
    main()
