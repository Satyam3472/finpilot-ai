"""Read and normalize bounded, local INR statements."""

import csv
import re
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from itertools import islice
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_XLSX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 100
INVALID_CELL = object()

ALIASES = {
    "date": {"date", "transaction_date"},
    "description": {"description", "narration"},
    "debit": {"debit", "withdrawal"},
    "credit": {"credit", "deposit"},
    "reference_id": {"reference_id", "transaction_reference"},
}
AMOUNT = re.compile(
    r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})"
    r"(?:\.[0-9]{1,2})?"
)
SENSITIVE_LABEL = re.compile(
    r"\b(?:account(?:\s+(?:number|no\.?))?|a/c)\s*[:=#-]?\s*[0-9]{6,}\b"
    r"|\b(?:password|passcode|pin|otp)\s*[:=#]\s*\S",
    re.IGNORECASE,
)


class StatementError(ValueError):
    """A validation error safe to show without revealing statement contents."""


def read_statement(path: Path) -> bytes:
    """Read one bounded snapshot for both hashing and parsing."""
    if path.suffix.lower() not in {".csv", ".xlsx"}:
        raise StatementError("Use a .csv or .xlsx statement.")
    if not path.is_file():
        raise StatementError("Choose an existing local file.")
    try:
        with path.open("rb") as file:
            content = file.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise StatementError("Cannot read the selected statement.") from None
    if len(content) > MAX_FILE_BYTES:
        raise StatementError("Statement exceeds the 5 MiB file limit.")
    return content


def parse_statement(path: Path, content: bytes | None = None) -> dict:
    """Return normalized records, row count, and row-level validation errors."""
    path = Path(path)
    if content is None:
        content = read_statement(path)
    if len(content) > MAX_FILE_BYTES:
        raise StatementError("Statement exceeds the 5 MiB file limit.")
    if path.suffix.lower() == ".csv":
        try:
            rows = csv.reader(StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
            return _parse_rows(rows)
        except (UnicodeError, csv.Error):
            raise StatementError("Invalid CSV. Use a UTF-8, comma-separated file.") from None
    if path.suffix.lower() != ".xlsx":
        raise StatementError("Use a .csv or .xlsx statement.")
    return _parse_xlsx(content)


def _parse_xlsx(content: bytes) -> dict:
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_XLSX_BYTES:
                raise StatementError("XLSX exceeds the 25 MiB expanded size limit.")
        # The second view detects formulas, including those with missing cached values.
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            formulas = load_workbook(BytesIO(content), read_only=True, keep_links=False)
            try:
                sheet = workbook.worksheets[0]
                formula_sheet = formulas.worksheets[0]
                sheet.reset_dimensions()
                formula_sheet.reset_dimensions()
                rows = zip(
                    sheet.iter_rows(max_col=MAX_COLUMNS + 1),
                    formula_sheet.iter_rows(max_col=MAX_COLUMNS + 1),
                    strict=True,
                )
                return _parse_rows(
                    tuple(
                        INVALID_CELL if formula.data_type == "f" or cell.data_type == "e"
                        else cell.value
                        for cell, formula in zip(values, raw, strict=True)
                    )
                    for values, raw in rows
                )
            finally:
                formulas.close()
        finally:
            workbook.close()
    except StatementError:
        raise
    except (BadZipFile, InvalidFileException, ParseError, ValueError, IndexError, KeyError, OSError):
        raise StatementError("Cannot read the first worksheet of this XLSX file.") from None


def _parse_rows(rows) -> dict:
    rows = iter(rows)
    header = list(next(rows, ()))
    while header and header[-1] is None:
        header.pop()
    if len(header) > MAX_COLUMNS:
        raise StatementError(f"Statement exceeds the {MAX_COLUMNS}-column limit.")
    names = [str(cell).strip().lower() for cell in header]
    columns = {}
    for field, aliases in ALIASES.items():
        matches = [index for index, name in enumerate(names) if name in aliases]
        if len(matches) > 1:
            raise StatementError(f"Multiple columns match {field}.")
        if matches:
            columns[field] = matches[0]
        elif field != "reference_id":
            raise StatementError(f"Missing required column: {field}.")

    records, errors = [], []
    for row_number, row in enumerate(islice(rows, MAX_ROWS + 1), start=2):
        if row_number > MAX_ROWS + 1:
            raise StatementError(f"Statement exceeds the {MAX_ROWS:,}-row limit.")
        if all(value is None or value == "" for value in row):
            continue
        try:
            if any(value is not None and value != "" for value in row[len(header):]):
                raise StatementError("Row contains values beyond the header.")
            fields = {
                field: row[index] if index < len(row) else None
                for field, index in columns.items()
            }
            records.append(_normalize(fields))
        except StatementError as error:
            errors.append({"row": row_number, "error": str(error)})
    return {"records": records, "errors": errors, "total_rows": len(records) + len(errors)}


def _normalize(fields: dict) -> dict:
    if any(value is INVALID_CELL for value in fields.values()):
        raise StatementError("Formulas and Excel error cells are unsupported.")
    description = fields["description"]
    if not isinstance(description, str) or not description.strip():
        raise StatementError("Description must contain text.")
    if SENSITIVE_LABEL.search(description):
        raise StatementError("Remove account identifiers or credentials from the description.")
    debit = parse_amount_minor(fields["debit"], "Debit")
    credit = parse_amount_minor(fields["credit"], "Credit")
    if bool(debit) == bool(credit):
        raise StatementError("Exactly one of debit or credit must be positive.")

    reference = fields.get("reference_id")
    if reference is not None and not isinstance(reference, (str, int)):
        raise StatementError("Reference ID must be text or an integer.")
    return {
        "transaction_date": _parse_date(fields["date"]),
        "description": description.strip(),
        "type": "expense" if debit else "income",
        "amount_minor": debit or credit,
        "currency": "INR",
        "reference_id": (str(reference).strip() or None) if reference is not None else None,
    }


def _parse_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                return date.fromisoformat(value).isoformat()
            named = re.fullmatch(r"([0-9]{1,2})[- ]([A-Za-z]{3})[- ]([0-9]{4})", value)
            if named:
                return datetime.strptime("-".join(named.groups()), "%d-%b-%Y").date().isoformat()
            numeric = re.fullmatch(r"([0-9]{1,2})([/\-])([0-9]{1,2})\2([0-9]{4})", value)
            if numeric:
                day, month, year = map(int, (numeric[1], numeric[3], numeric[4]))
                if day <= 12 and day != month:
                    raise ValueError
                return date(year, month, day).isoformat()
        except ValueError:
            pass
    raise StatementError("Invalid or ambiguous date. Use YYYY-MM-DD or a named month.")


def parse_amount_minor(value: object, label: str) -> int:
    """Parse an INR amount as integer paise, treating a blank statement cell as zero."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0
    text = str(value).strip()
    if not AMOUNT.fullmatch(text) or len(text) > 20:
        raise StatementError(f"{label} must be a nonnegative INR amount with at most two decimals.")
    amount = Decimal(text.replace(",", ""))
    if amount > 1_000_000_000_000:
        raise StatementError(f"{label} exceeds the supported amount limit.")
    return int(amount * 100)
