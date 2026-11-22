"""Transaction browsing and bounded statement ingestion."""

import re
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from backend.schemas import Category, ImportBatch, ImportResult, Month, TransactionPage
from finance_agent import database
from finance_agent.budget import CATEGORIES
from finance_agent.import_service import import_statement
from finance_agent.parser import MAX_FILE_BYTES, StatementError

router = APIRouter()
SORT_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}


@router.get("/transactions", response_model=TransactionPage)
def transactions(
    month: Month | None = None,
    category: Category | None = None,
    type: Literal["income", "expense"] | None = None,
    search: Annotated[str, Query(max_length=120)] = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["asc", "desc"] = "desc",
) -> dict:
    conditions, values = [], []
    if month:
        conditions.append("transaction_date BETWEEN ? AND ?")
        values.extend((f"{month}-01", f"{month}-31"))
    if category:
        if category not in {*CATEGORIES, "income"}:
            raise HTTPException(422, "Unknown transaction category.")
        conditions.append("category = ?")
        values.append(category)
    if type:
        conditions.append("type = ?")
        values.append(type)
    if search := search.strip():
        conditions.append("(instr(lower(description), lower(?)) > 0 OR instr(lower(merchant), lower(?)) > 0)")
        values.extend((search, search))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    direction = SORT_DIRECTIONS[sort]
    items, total = [], 0
    if database.DB_PATH.is_file():
        with closing(database.connect(read_only=True)) as connection, connection:
            connection.execute("BEGIN")
            total = connection.execute(f"SELECT COUNT(*) FROM transactions {where}", values).fetchone()[0]
            items = [
                dict(row) for row in connection.execute(
                    f"""
                    SELECT id, transaction_date AS date, merchant, description, category, type,
                           amount_minor, currency, needs_review
                    FROM transactions {where}
                    ORDER BY transaction_date {direction}, id {direction}
                    LIMIT ? OFFSET ?
                    """,
                    (*values, page_size, (page - 1) * page_size),
                )
            ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/statements/upload", response_model=ImportResult, status_code=201, responses={
    200: {"model": ImportResult, "description": "Identical statement already imported"},
})
def upload(response: Response, file: Annotated[UploadFile, File(description="CSV or XLSX, up to 5 MiB")]) -> dict:
    original = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(original).suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise HTTPException(415, "Upload a CSV or XLSX statement.")
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Statement exceeds the 5 MiB file limit.")
    stem = re.sub(r"[^\w .()-]", "_", Path(original).stem)[:120].strip(" .") or "statement"
    with TemporaryDirectory(prefix="finpilot-upload-") as folder:
        path = Path(folder) / f"{stem}{extension}"
        path.write_bytes(content)
        try:
            result = import_statement(path)
        except StatementError as error:
            raise HTTPException(422, str(error)) from error
    if result["already_imported"]:
        response.status_code = 200
    return result


@router.get("/imports", response_model=list[ImportBatch])
def import_history() -> list[dict]:
    return [
        dict(row) for row in database.fetch_rows(
            """
            SELECT id, file_name, imported_at, total_rows, imported_rows, rejected_rows, status
            FROM import_batches ORDER BY imported_at DESC, id DESC LIMIT ?
            """,
            (100,),
        )
    ]
