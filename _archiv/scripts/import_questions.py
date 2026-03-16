#!/usr/bin/env python3
"""
Imports a questions CSV where column headers = competency legacy IDs.
Delegates to /admin/import/questions endpoint.

Usage:
    python import_questions.py --csv path/to/fragen.csv
    --api https://dashboard.schule.de --cookie session_cookie_value
"""
import argparse
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to questions CSV (columns = competency IDs)")
    parser.add_argument("--api", default="https://dashboard.schule.de")
    parser.add_argument("--cookie", required=True)
    args = parser.parse_args()

    session = requests.Session()
    session.cookies.set("session", args.cookie)

    print(f"Importing questions from {args.csv}...")
    with open(args.csv, "rb") as f:
        resp = session.post(
            f"{args.api}/api/admin/import/questions",
            files={"file": (args.csv, f, "text/csv")},
        )
    resp.raise_for_status()
    result = resp.json()
    print(f"Imported: {result['imported']}, Skipped: {result['skipped']}")
    for w in result.get("warnings", []):
        print(f"WARNING: {w}")


if __name__ == "__main__":
    main()
