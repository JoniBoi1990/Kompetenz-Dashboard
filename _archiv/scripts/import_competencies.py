#!/usr/bin/env python3
"""
Standalone migration script — imports kompetenzen.json then enriches from CSV.
Can be run directly against a live API or used as a reference for the /admin/import endpoints.

Usage:
    python import_competencies.py --json path/to/kompetenzen.json --csv path/to/kompetenzen.csv
    --api https://dashboard.schule.de --cookie session_cookie_value
"""
import argparse
import json
import sys
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="Path to kompetenzen.json")
    parser.add_argument("--csv", help="Path to Kompetenz CSV")
    parser.add_argument("--api", default="https://dashboard.schule.de", help="API base URL")
    parser.add_argument("--cookie", required=True, help="Session cookie value")
    args = parser.parse_args()

    session = requests.Session()
    session.cookies.set("session", args.cookie)
    session.headers["Accept"] = "application/json"

    if args.json:
        print(f"Importing competencies from {args.json}...")
        with open(args.json, "rb") as f:
            resp = session.post(
                f"{args.api}/api/admin/import/competencies",
                files={"file": (args.json, f, "application/json")},
            )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Imported: {result['imported']}, Skipped: {result['skipped']}")
        for w in result.get("warnings", []):
            print(f"  WARNING: {w}")

    if args.csv:
        print(f"Enriching from CSV {args.csv}...")
        with open(args.csv, "rb") as f:
            resp = session.post(
                f"{args.api}/api/admin/import/competencies",
                files={"file": (args.csv, f, "text/csv")},
            )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Updated: {result['imported']}, Skipped: {result['skipped']}")
        for w in result.get("warnings", []):
            print(f"  WARNING: {w}")

    # Check final status
    resp = session.get(f"{args.api}/api/admin/import/status")
    resp.raise_for_status()
    status = resp.json()
    print(f"\nFinal DB state: {status['competencies']} competencies, {status['questions']} questions")


if __name__ == "__main__":
    main()
