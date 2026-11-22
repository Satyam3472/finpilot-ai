"""HTTP contracts shared by the finance routers."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from finance_agent.analytics import validate_month

Currency = Literal["INR"]


def check_month(value: str) -> str:
    if error := validate_month(value):
        raise ValueError(error["error"])
    return value


Month = Annotated[str, StringConstraints(min_length=7, max_length=7), AfterValidator(check_month)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class BudgetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: Annotated[int, Field(strict=True, ge=0, le=100_000_000_000_000)]


class ChatWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: MessageText


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatSession(BaseModel):
    id: str
    title: str
    updated_at: float


class ChatHistory(ChatSession):
    messages: list[ChatMessage]


class Transaction(BaseModel):
    id: int
    date: str
    merchant: str | None
    description: str
    category: str
    type: Literal["income", "expense"]
    amount_minor: int
    currency: Currency
    needs_review: bool


class TransactionPage(BaseModel):
    items: list[Transaction]
    total: int
    page: int
    page_size: int


class RowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    total_rows: int
    imported_rows: int
    rejected_rows: int
    uncategorized_transactions: int
    potential_duplicates: int
    already_imported: bool
    errors: list[RowError]


class ImportBatch(BaseModel):
    id: int
    file_name: str
    imported_at: str
    total_rows: int
    imported_rows: int
    rejected_rows: int
    status: Literal["imported", "partial", "rejected"]


class Budget(BaseModel):
    month: Month
    category: str
    currency: Currency
    budget_minor: int
    spent_minor: int | None
    remaining_minor: int | None
    utilization_percent: float | None
    status: Literal["insufficient_data", "over_budget", "within_budget"]


class BudgetSummary(BaseModel):
    month: Month
    currency: Currency
    has_imported_records: bool
    status: str
    overall_utilization_percent: float | None
    budgets: list[Budget]
    categories: list[str]


class Dashboard(BaseModel):
    month: Month
    availability: Literal["has_records", "no_records"]
    currency: Currency
    total_income_minor: int | None
    total_expenses_minor: int | None
    net_cash_flow_minor: int | None
    transaction_count: int
    category_totals_minor: dict[str, int]
    budget_summary: BudgetSummary


def minor(value: int | float | None) -> int | None:
    """Adapt the existing ADK tools' INR results to integer API amounts."""
    return None if value is None else round(Decimal(str(value)) * 100)


def minor_fields(record: dict, *fields: str) -> dict:
    result = dict(record)
    for field in fields:
        result[f"{field}_minor"] = minor(result.pop(field, None))
    return result
