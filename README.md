# FinPilot AI

FinPilot AI is a Google ADK team for personal finance. It can explain
budgeting and draft illustrative plans from figures you provide. Phase 3
added local CSV and XLSX imports with deterministic SQLite analytics.
Phase 4 adds a coordinator and three specialists that share those read-only
analytics tools.
Phase 5 adds spending history, monthly comparisons, explainable unusual
expense flags, and configurable budgets.

## Phase 7 local container setup

Phase 7 adds authenticated local access, a same-origin API proxy, persistent
Docker storage, liveness and readiness checks, and backup and restore tools.
From the existing virtual environment:

```bash
python -m pip install -r requirements.lock
python -m scripts.configure_local
docker compose config --quiet
docker compose up --build -d
```

Open [FinPilot](http://localhost:3000/login). The frontend is the only
published service. Use `docker compose down` to stop it and retain data.
See [Production readiness](docs/production-readiness.md) for secrets,
local setup, evaluation, recovery, and verified results.

## Phase 6 application

FinPilot now has a six-page Next.js application for imported records,
budget management, analytics, and Google ADK chat. The Python modules
below remain the source of the financial calculations.

### Stack and architecture

- **Web** uses Next.js App Router, React, strict TypeScript, Tailwind CSS,
  shadcn/ui Button and Dialog components, Lucide icons, Recharts, Geist,
  and Sonner notifications.
- **API** uses FastAPI, Pydantic, and Uvicorn. The finance routers adapt
  the existing Python services. Transactions use parameterized SQLite
  queries with fixed date sorting and pagination. API monetary amounts
  are integer paise, and the frontend formats them with `Intl.NumberFormat`.
- **Assistant** uses the existing FinPilot Coordinator and its Transaction
  Analyst, Budget Planner, and Expense Insights specialists. FastAPI
  invokes ADK's `Runner` and `SqliteSessionService` with one configured
  local identity. This wrapper exposes only user messages and coordinator
  text through JSON history and SSE. The generic ADK API's internal event,
  artifact, and arbitrary-identity routes are kept separate.
- **Storage** uses `.finpilot/transactions.sqlite3` for transactions,
  import batches, and monthly budgets. ADK events and sessions live in
  `.finpilot/chat_sessions.sqlite3`. Both databases are local and ignored
  by Git. The private data directory can be overridden for isolated testing.

```text
finpilot-ai/
├── backend/                 # App, request/response contracts, API routers
├── finance_agent/           # Existing agent team, imports, SQLite, analytics
├── frontend/
│   ├── src/app/             # Six App Router pages
│   ├── src/components/      # Navigation, charts, tables, dialogs, states
│   ├── src/hooks/           # Abortable data loading
│   ├── src/lib/             # Typed API, SSE, formatting
│   └── e2e/                 # Playwright journeys
├── scripts/                 # Local import and budget commands
├── sample_data/             # Synthetic fixtures
└── tests/                   # Existing tests plus FastAPI integration tests
```

### Run the full stack

Use Python 3.11+ and Node.js 20.9+ (Node 24 used for verification).
From the project root, activate the Python environment and install dependencies.

```bash
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m scripts.configure_local
uvicorn backend.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [FinPilot](http://localhost:3000/login) or [API health](http://localhost:8000/api/health/live). The default commands bind to
loopback. To run the previous standalone ADK Web interface, stop FastAPI
or use a different port for ADK Web, such as `adk web --port 8001`.

| Variable | Location and behavior |
| --- | --- |
| `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` | Configure `finance_agent/.env` from its template for Gemini chat. The backend loads it. The other finance features work without a Gemini key. |
| `FINPILOT_LOCAL_USER` | Server-owned session identity. Defaults to `finpilot-local`; keep it stable to retrieve the same conversations. |
| `FINPILOT_DATA_DIR` | Optional private storage directory for the API, ADK tools, and CLI. Defaults to `.finpilot/` at the project root. Set it before startup to isolate demo data. |
| `FINPILOT_BACKEND_URL` | Frontend server only; defaults to `http://127.0.0.1:8000`. Browser requests use the frontend origin. |

For optional backend settings, copy `backend/.env.example` and launch with
`uvicorn backend.main:app --env-file backend/.env --reload --port 8000`,
or export the values in the shell. The frontend template is
`frontend/.env.example`.

### Pages and API

| Web route | What you can do |
| --- | --- |
| `/dashboard` | Select a month, view figures and charts, and open recent transactions or budget alerts. It opens on the latest imported month when available. |
| `/transactions` | Filter by month, category, type, or search, and page through date-sorted records. |
| `/imports` | Upload CSV/XLSX and review rejected rows, duplicate notices, and import history. |
| `/budgets` | Set a monthly category allocation, view utilization, and explicitly edit or delete it. |
| `/analytics` | Review historical cash flow, compare expenses, inspect anomaly candidates, and read savings observations. |
| `/assistant` | Start or reopen a conversation, send a message, and see streamed coordinator text when available. |

| HTTP endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Process health. |
| `GET /api/dashboard/summary?month=YYYY-MM` | Cash flow, categories, record availability, and budget totals; month is optional. |
| `GET /api/transactions` | Filters `month`, `category`, `type`, `search`, `page`, `page_size`, `sort`. |
| `POST /api/statements/upload` | Multipart `file`, validated CSV/XLSX up to 5 MiB. |
| `GET /api/imports` | Up to 100 latest import batches. |
| `GET /api/budgets?month=YYYY-MM` | Saved allocations and utilization. |
| `PUT /api/budgets/{month}/{category}` | Create or update with JSON `{"amount_minor": 800000}` for ₹8,000. |
| `DELETE /api/budgets/{month}/{category}` | Remove an allocation with no change to transaction data. |
| `GET /api/analytics/trends?months=6` | Spending history ending at the latest imported month. |
| `GET /api/analytics/comparison?month1=YYYY-MM&month2=YYYY-MM` | Comparison using the first month as the baseline. |
| `GET /api/analytics/anomalies?month=YYYY-MM` | Statistical candidates and coverage limitations. |
| `GET /api/insights/savings?month=YYYY-MM` | Evidence and possible budget actions. |
| `GET /api/chat/sessions`, `POST /api/chat/sessions` | List or create conversations for the configured local identity. |
| `GET /api/chat/sessions/{id}` | Retrieve the user-facing transcript. |
| `POST /api/chat/sessions/{id}/messages` | Submit JSON `{"message":"…"}`; streams `delta`, `done`, or `error` events. |

HTTP errors use `{"error":{"code":"…","message":"…"}}`. Failures after a chat
stream starts are sent as sanitized SSE error events. Conversation history
persists across backend restarts. The browser keeps the selected session
in the route so it can restore the same conversation on refresh.

### Import a demo

In a clean demo workspace, open **Import statements** and select
`sample_data/analytics_statement.csv`. October 2026 should show ₹60,000 income,
₹5,312 expenses, and ₹54,688 net cash flow. Add a ₹2,000 October food
budget to see an over-budget alert. August has no statement data and
is shown as missing. The older fixture and CLI remain available below.

### Phase 6 checks

```bash
python -m unittest discover -s tests -v
cd frontend
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

The browser suite starts its own frontend and API on ports 3000 and 8000
with temporary SQLite storage, so stop other processes on those ports first.
Use `FINPILOT_BROWSER=chrome npm run test:e2e` if Chrome is already installed.
The finance journeys use the real API and synthetic data. The browser chat
test mocks the API to verify loading, recovery, and restoration. The
Python chat integration test uses the actual ADK runner and SQLite tools
with scripted model decisions. Neither test suite needs a Gemini key.

### Screenshots

[Dashboard](docs/screenshots/dashboard.png) · [Analytics](docs/screenshots/analytics.png)

Both screenshots use the synthetic statement. Run
`FINPILOT_CAPTURE_SCREENSHOTS=1 npm run test:e2e` in `frontend/` to recapture them.

### Local privacy and limitations

FinPilot is a **single-user localhost application**. The finance and chat
APIs require an authenticated session. Mutating requests require a valid
origin and CSRF token. Keep the published frontend on loopback.

Statement parsing and storage are local. Chat and selected tool results
go to Gemini during inference. Raw statement text and specialist traces
are excluded from chat API responses, and the existing assistant tools
do not send raw transaction descriptions. Databases and session events
are not encrypted by the app. Use synthetic data for demonstrations,
and keep real statement files out of the repository. AI responses can be
unavailable due to provider configuration, quota, or service errors.
Anomaly candidates indicate possible outliers and cannot establish fraud.

### Optional future work

A local transaction review workflow could add explicit confirmation for
changes to flagged expenses, uncategorized records, and duplicate candidates.

## Project structure

```text
finpilot-ai/
├── finance_agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── analytics.py
│   ├── anomaly.py
│   ├── budget.py
│   ├── insights.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── transaction_agent.py
│   │   ├── budget_agent.py
│   │   └── insights_agent.py
│   ├── data.py                 # Optional legacy October 2026 budget defaults
│   ├── parser.py
│   ├── categorizer.py
│   ├── database.py
│   ├── import_service.py
│   ├── tools.py
│   ├── .env                    # Local Gemini configuration
│   └── .env.example
├── scripts/
│   ├── __init__.py
│   ├── import_statement.py
│   └── manage_budget.py
├── sample_data/
│   ├── analytics_statement.csv
│   └── sample_statement.csv
├── tests/
│   ├── test_agents.py
│   ├── test_analytics.py
│   ├── test_anomaly.py
│   ├── test_budget.py
│   ├── test_categorizer.py
│   ├── test_import.py
│   ├── test_parser.py
│   └── test_tools.py
├── .gitignore
├── README.md
└── requirements.txt
```

## Setup

Use Python 3.11 or newer and a Gemini API key from Google AI Studio. The
project uses the official `google-adk` 2.x package. It uses
`gemini-flash-latest`, the Gemini Flash alias shown in Google's
[ADK Python quickstart](https://adk.dev/get-started/python/). The model
behind the alias can change. API requests require a valid key and
available quota.

From the project root, create a virtual environment using your Python
3.11+ interpreter. If your system exposes it as `python3`, use that
command in the first step.

```bash
python -m venv .venv
```

Activate on macOS or Linux.

```bash
source .venv/bin/activate
```

Activate on Windows PowerShell.

```powershell
.venv\Scripts\Activate.ps1
```

Install the dependency.

```bash
python -m pip install -r requirements.txt
```

If `finance_agent/.env` is absent, copy `finance_agent/.env.example` there.
Replace `your_gemini_api_key_here` with your key and keep
`GOOGLE_GENAI_USE_VERTEXAI=FALSE` to use the Gemini API through AI Studio.
Git ignores the local `.env` file. [Google AI Studio API keys](https://aistudio.google.com/apikey)

## Import and run

From the project root with the virtual environment active, import the
synthetic statement using the local CLI. The import works without a Gemini key.

```bash
python -m scripts.import_statement sample_data/sample_statement.csv
```

```text
Rows: 6 | Imported: 6 | Rejected: 0 | Uncategorized: 0 | Potential overlaps: 0
```

Then run ADK Web with a valid Gemini key.

```bash
adk web --port 8000
```

Open [http://localhost:8000](http://localhost:8000), select `finance_agent`,
and try the prompts in [Routing checks](#routing-checks).

## Statement format

Use UTF-8 comma-separated CSV (an optional BOM is accepted) or the first
worksheet of an XLSX file. Put the header in the first row. Header names
are trimmed and case-insensitive.

| Required column | Accepted alias |
| --- | --- |
| `date` | `transaction_date` |
| `description` | `narration` |
| `debit` | `withdrawal` |
| `credit` | `deposit` |

`reference_id` or `transaction_reference` is optional. Use text cells for
reference IDs with leading zeroes. Other columns are ignored.

- Use ISO dates such as `2026-10-02`, named-month dates such as
  `2-Oct-2026` or `2 Oct 2026`, or unambiguous day-first dates such as
  `15/10/2026` or `15-10-2026`. Ambiguous numeric dates such as
  `04/05/2026` are rejected. Excel date or datetime cells are accepted,
  and stored dates use `YYYY-MM-DD`.
- Each row needs a description and exactly one positive debit or credit.
  Leave the other amount blank or set it to zero. Debit is an expense and
  credit is income for this app. Amounts accept up to two decimal places
  and valid Indian or Western comma grouping. Quote grouped amounts in CSV.
  Currency is INR, and amounts are stored as integer paise using `Decimal`.
- Use plain values in the supported columns. Formula cells in those columns
  are rejected, including formulas with cached values. Excel error cells
  are rejected there too. Limits are 5 MiB per file, 25 MiB expanded for
  XLSX, 10,000 data rows, and 100 header columns. Blank rows are skipped.
- Descriptions are retained with surrounding whitespace trimmed. Keep
  account numbers, passwords, PINs, and other secrets out of descriptions
  and reference IDs. Validation rejects some explicitly labeled sensitive
  text, and cannot reliably identify every sensitive value.

## How imports work

1. The CLI reads one bounded file snapshot and computes its SHA-256 hash.
2. The parser maps headers, validates rows, and returns normalized values
   with row numbers and reasons for rejected rows. It leaves raw values out
   of validation messages.
3. Local rules match whole words and phrases. Known names such as Zomato,
   Uber, and Amazon get canonical merchant names and categories. Keywords
   such as `flat rent` can set the category without naming a merchant.
   Credits go to `income`. Unmatched expenses go to `uncategorized` and
   are marked for review.
4. SQLite checks the file hash under a write lock. Valid rows and batch
   metadata commit together. Files with at least one committed row, including
   partial imports, are skipped on exact retries. Potential overlaps with
   earlier imports are flagged by reference ID or matching date, direction,
   amount, and case-insensitive description. Flagged rows are retained and
   still contribute to totals.

SQLite stores the data in `.finpilot/transactions.sqlite3`, under a
Git-ignored directory. The `import_batches` table records the filename,
file hash, UTC timestamp, row counts, and batch status. The `transactions`
table links each normalized record to its batch and stores amount, category,
merchant, rule provenance, reference ID, and review flags. Date, category,
transaction type, and reference indexes support lookups.

## Phase 4 agent architecture

| Agent | Responsibility |
| --- | --- |
| `finpilot_coordinator` | Receives user requests, answers general finance questions, delegates stored-data work, and combines the findings. |
| `transaction_analyst` | Reports income, expenses, category totals, largest expenses, net cash flow, and historical comparisons. |
| `budget_planner` | Checks saved monthly allocations, reports utilization, and suggests actions supported by spending and budget evidence. |
| `expense_insights` | Identifies top expenses and categories, compares periods, and explains unusually large expenses. |

ADK loads the coordinator as `root_agent`. Its `sub_agents` list makes
the specialists its children, and they inherit its Gemini model. ADK exposes
each `mode="single_turn"` child as a delegation tool named after that
child. The coordinator gives it a focused request. The specialist can
make multiple model and tool calls within that task, then returns its
findings automatically, without interacting directly with the user.
The coordinator can use the findings in later delegations and write the
final answer. [ADK collaborative workflows](https://adk.dev/workflows/collaboration/)

Gemini chooses whether to delegate and which calls to make. Routing,
call order, and the number of specialists can vary. Each specialist has
only its assigned finance tools. The coordinator has ADK-generated
delegation tools and no direct SQLite tools.

ADK sessions hold conversation history and execution events, and session
state can carry temporary conversational context. The separate transaction
database in `.finpilot/transactions.sqlite3` is the source for imported
financial records. A new ADK conversation can query those same records.

### Routing checks

In ADK Web, start with a fresh session and ask the following questions
using the synthetic statement. Run D after A in the same session so
“October” has a clear year. For B, configure the original October
allocation with `python -m scripts.manage_budget seed-legacy` and specify
October 2026 if the coordinator asks for the month.

| Check | Prompt | Expected route and outcome |
| --- | --- | --- |
| A | How much did I spend in October 2026? | Transaction Analyst calls `get_total_expenses` and reports ₹4,228. |
| B | How much food budget do I have left? | Budget Planner calls `calculate_remaining_budget` and reports ₹7,200 for October 2026. |
| C | What are my largest expenses? | Expense Insights or Transaction Analyst calls `get_largest_transactions` and reports shopping ₹2,499 first. |
| D | Analyze my October spending, identify the biggest categories, and suggest budget improvements. | Relevant specialists cover the total, top categories, and budget suggestions. The coordinator combines their findings. |
| E | Explain the 50/30/20 budgeting rule. | The coordinator can answer directly. |
| F | Compare my expenses for January and February 2026. | Expense Insights checks both periods and explains that the sample has no records for either. |

Open **Trace** for the user turn. Inspect the coordinator's function call
for the specialist name and request. Then inspect the specialist's finance
tool calls and results, its return to the coordinator, and the coordinator's
final response. For E, check for a direct model response without a
delegation call. [ADK Trace view](https://adk.dev/evaluate/#debugging-with-the-trace-view)

## ADK finance tools

Gemini chooses a registered tool and supplies its arguments. ADK calls
the Python function, which reads SQLite and returns calculated figures
for Gemini to explain. [ADK function tools](https://adk.dev/tools-custom/function-tools/)

| Tool | Example question and expected result after importing the sample |
| --- | --- |
| `get_total_expenses(month)` | “How much did I spend in October 2026?” → ₹4,228 across five expenses. |
| `get_expenses_by_category(month)` | “Break down October 2026 expenses by category.” → Food ₹800, shopping ₹2,499, travel ₹280, entertainment ₹649. |
| `get_largest_transactions(limit=5)` | “What are my three biggest expenses?” → ₹2,499 shopping, ₹649 entertainment, ₹450 food. |
| `calculate_remaining_budget(category)` | “How much is left in the October food budget?” → ₹7,200 after saving an ₹8,000 allocation for October 2026. |
| `get_transaction_summary(month)` | “Summarize my October 2026 cash flow.” → ₹60,000 income, ₹4,228 expenses, ₹55,772 net, six records. |

Months without imported rows return a no-data message. An income-only
month returns zero imported expenses. Imported rows can cover part of a
month, and overlapping files can overstate totals. General questions such
as “Explain the 50/30/20 rule” can be answered without reading SQLite.

## Phase 5 analytics and budgets

Historical and budget calculations use integer paise and return INR.
Spending trends cover 1–24 calendar months, ending at the **latest
imported month**. Missing months appear with null amounts. Comparisons
use the first month as the baseline, return the magnitude of the INR
change and a signed percentage, and return a null percentage if the
baseline is zero. Imported rows may cover only part of a month.

### Explainable unusual expenses

The detector compares an expense against the previous 12 calendar months
of expenses in the same category. It excludes the entire selected month
and all future records from the baseline. At least five prior expenses
are required. The tool computes `0.6745 × (amount − median) / MAD`, where
MAD is the median of the absolute differences from the baseline median.
It flags positive scores above 3.5 and returns the 20 highest-scoring
results at most. A zero MAD prevents scoring, and uncategorized expenses
are skipped because they lack a meaningful comparison group.
[NIST on modified Z-scores](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm)

Scores measure distance from past spending under this rule. They can be
affected by duplicate records, partial statement coverage, changes in
spending habits, and categories that contain different kinds of purchases.
Flags are review prompts. They do not establish fraud.

### Configure budgets locally

From the project root, with the virtual environment active:

```bash
python -m scripts.manage_budget set --month 2026-10 --category food --amount 8000
python -m scripts.manage_budget list --month 2026-10
python -m scripts.manage_budget delete --month 2026-10 --category food
```

The additive migration creates `monthly_budgets` during a statement
import or budget write while preserving existing records and import
history. Pre-migration databases are readable. The table stores a unique
month/category pair, integer paise, and creation and update timestamps.
Amounts can be zero. Zero budgets have undefined utilization and go
over budget when observed spending is positive. Allocations with no
imported records have unknown spending and remaining amounts.

Use `python -m scripts.manage_budget seed-legacy` to explicitly copy
the Phase 2 October 2026 defaults, leaving configured values intact.
Rerunning it skips existing entries and can restore deleted defaults.
The legacy `calculate_remaining_budget(category)` still looks up October
2026. New tools take an explicit month. Agents can read allocations.
Use the local CLI or the Budgets page to make an explicit change.

### New tools and ADK Web checks

Use a clean synthetic demo workspace for these examples. Import
`sample_data/analytics_statement.csv` instead of the Phase 3 sample,
then set October food to ₹2,000, shopping to ₹1,700, and travel to ₹0.
Run `adk web --port 8000`, select `finance_agent`, and inspect specialist
delegation, tool arguments, and results in **Trace**. Give the year and
budget month if they aren't established in the conversation.

| Prompt | Tool and expected result |
| --- | --- |
| Compare my September and October expenses. | `compare_monthly_expenses` → ₹2,520 to ₹5,312, up ₹2,792 (110.79%). |
| Show my spending trend for the last six months. | `get_monthly_spending_trend` → ends in October 2026 and shows August as missing. |
| Did I have any unusually large expenses in October? | `detect_unusual_transactions` → flags a ₹2,000 food expense and explains the history and zero-deviation limits. |
| How much of my food budget have I used? | `get_budget_utilization` → 105.6% used and ₹112 over the October budget. |
| Show all my October budgets. | `get_budget_summary` → saved allocations with spending, remaining amounts, and utilization where defined. |
| Where could I reduce spending? | `get_savings_opportunities` → shows budget pressure and higher shopping spending than in September. |
| Compare two months for which I have no data. | `compare_monthly_expenses` → use January and February 2026 and confirm neither returns a spending total. |
| Is this unusual transaction fraudulent? | Explains that the statistical flag cannot establish fraud. |

Savings observations compare the requested month to the previous calendar
month when records exist. The tool flags utilization of at least 80% or
overspending, and rising shopping or entertainment spending. Suggested
actions are separate from the evidence and carry no estimated savings or
forecast.

## Privacy and limitations

Statement ingestion and categorization run locally. ADK tools return dates,
categories, and calculated figures where relevant. Chat inputs and tool
results go to Gemini when you use ADK Web. Descriptions, merchant names,
and reference IDs stay out of tool responses. Use synthetic data for
demonstrations and keep personal source files outside the repository.
The local SQLite file is not encrypted by the app.

This single-user workflow supports a narrow statement layout and one
currency. It has no connection to banks and does not verify statement
completeness or distinguish salary from refunds and transfers within
credits. Review flags are stored for future workflows. Budget settings
apply only to the month and category explicitly configured.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic files and temporary SQLite databases and require no
Gemini credentials or network calls. The delegation test scripts model
decisions while running the real ADK dispatch and SQLite tools.
