import io
import json
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from auth.dependencies import require_teacher
from db.session import get_db
from models.models import Competency, Question, User
from schemas.schemas import ImportResult

router = APIRouter()


@router.post("/import/competencies", response_model=ImportResult)
async def import_competencies(
    file: UploadFile = File(...),
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    warnings = []
    imported = 0
    skipped = 0

    if file.filename.endswith(".json"):
        data = json.loads(content)
        for item in data:
            legacy_id = item.get("id")
            name = item.get("name", "").strip()
            typ = item.get("typ", "")
            if typ not in ("einfach", "niveau"):
                warnings.append(f"Unknown typ '{typ}' for legacy_id {legacy_id}, skipped")
                skipped += 1
                continue

            stmt = pg_insert(Competency).values(
                id=str(uuid.uuid4()),
                legacy_id=legacy_id,
                name=name,
                typ=typ,
                display_order=legacy_id or 0,
            ).on_conflict_do_nothing(index_elements=["legacy_id"])
            result = await db.execute(stmt)
            if result.rowcount:
                imported += 1
            else:
                skipped += 1

    elif file.filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), delimiter=";")
        df.columns = df.columns.str.strip()
        required = {"ID", "Kompetenz"}
        if not required.issubset(df.columns):
            raise HTTPException(status_code=400, detail=f"CSV must have columns: {required}")

        for _, row in df.iterrows():
            legacy_id = int(row["ID"]) if pd.notna(row["ID"]) else None
            if legacy_id is None:
                skipped += 1
                continue

            result = await db.execute(select(Competency).where(Competency.legacy_id == legacy_id))
            comp = result.scalar_one_or_none()

            update_data = {}
            if "BP-Nummer" in df.columns and pd.notna(row.get("BP-Nummer")):
                update_data["bp_nummer"] = str(row["BP-Nummer"]).strip()
            if "Thema" in df.columns and pd.notna(row.get("Thema")):
                update_data["thema"] = str(row["Thema"]).strip()
            if "Anmerkungen" in df.columns and pd.notna(row.get("Anmerkungen")):
                update_data["anmerkungen"] = str(row["Anmerkungen"]).strip()

            if comp is None:
                name = str(row["Kompetenz"]).strip()
                typ_col = str(row.get("Typ", "einfach")).strip().lower() if "Typ" in df.columns else "einfach"
                comp = Competency(
                    id=str(uuid.uuid4()),
                    legacy_id=legacy_id,
                    name=name,
                    typ=typ_col if typ_col in ("einfach", "niveau") else "einfach",
                    display_order=legacy_id,
                    **update_data,
                )
                db.add(comp)
                imported += 1
            else:
                for k, v in update_data.items():
                    setattr(comp, k, v)
                imported += 1
    else:
        raise HTTPException(status_code=400, detail="Only .json and .csv files supported")

    return ImportResult(imported=imported, skipped=skipped, warnings=warnings)


@router.post("/import/questions", response_model=ImportResult)
async def import_questions(
    file: UploadFile = File(...),
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content), delimiter=";")
    df.columns = df.columns.str.strip().astype(str)

    imported = 0
    skipped = 0
    warnings = []

    for col in df.columns:
        try:
            legacy_id = int(float(col))
        except (ValueError, TypeError):
            warnings.append(f"Column '{col}' is not a numeric competency ID, skipped")
            skipped += 1
            continue

        result = await db.execute(select(Competency).where(Competency.legacy_id == legacy_id))
        comp = result.scalar_one_or_none()
        if comp is None:
            warnings.append(f"No competency with legacy_id={legacy_id} (column '{col}'), skipped")
            skipped += 1
            continue

        texts = df[col].dropna().astype(str).str.strip().tolist()
        for text in texts:
            if not text:
                continue
            existing = await db.execute(
                select(Question).where(
                    Question.competency_id == comp.id,
                    Question.text == text,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            q = Question(id=str(uuid.uuid4()), competency_id=comp.id, text=text)
            db.add(q)
            imported += 1

    return ImportResult(imported=imported, skipped=skipped, warnings=warnings)


@router.get("/import/status")
async def import_status(
    _teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    comp_count = await db.execute(select(func.count()).select_from(Competency))
    q_count = await db.execute(select(func.count()).select_from(Question))
    return {
        "competencies": comp_count.scalar(),
        "questions": q_count.scalar(),
    }
