# Phase 7 production readiness

FinPilot runs locally as a single-user application. The Compose setup is a
deployment candidate for a private workstation. A public release would
require a deployment-specific security and operations review.

## Architecture

The browser calls the Next.js origin on port 3000. A server-only route
handler validates the API path and method, forwards requests to the configured
FastAPI origin, and returns JSON, file-import responses, or streaming chat
text. The proxy forwards only the headers needed for cookies, CSRF,
and content type, and injects the container trust secret on the server.

Compose publishes only `127.0.0.1:3000` by default. Both services join an
internal network for the proxy connection. A separate backend bridge
permits outbound Gemini calls. The frontend joins a separate bridge for
the published port. Both runtimes run under non-root UIDs with read-only
root filesystems, dropped capabilities, and no-new-privileges. Health
checks use Python and Node already present in the runtime images. The
backend uses one Uvicorn worker with graceful shutdown.

| Volume file | Purpose |
| --- | --- |
| `transactions.sqlite3` | Imported transactions, batches, and monthly budgets |
| `chat_sessions.sqlite3` | ADK conversations and events |
| `auth.sqlite3` | Revocable login sessions and login throttle |

The named volume mounts at `/data`. Startup initializes missing tables
without resetting records. The local configuration uses `.finpilot/` or
the directory specified by `FINPILOT_DATA_DIR`. Keep the configured ADK
identity stable when moving existing conversation data.

## Start and stop

With the existing Python environment and Docker Desktop running:

```bash
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m scripts.configure_local
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

The setup command prompts for the single-user password and Gemini key even
before the application runs. It writes the Argon2id hash and random keys
into `.secrets/` and preserves existing files. Open [FinPilot](http://localhost:3000/login)
and sign in with the password you chose. For a deliberate reduced-function
start without Gemini, use `python -m scripts.configure_local --without-gemini`
and `FINPILOT_REQUIRE_GEMINI=0 docker compose up --build -d`. Gemini-backed
chat still requires valid credentials.

```bash
curl -fsS http://localhost:3000/api/health/live
curl -fsS http://localhost:3000/api/health/ready
docker compose logs -f backend
docker compose restart backend
docker compose down
```

`down` preserves the named volume. To resume, use `docker compose up -d`.
Use the same Compose project name to reopen its data.

### Configuration reference

| Setting | Default or purpose |
| --- | --- |
| `FINPILOT_SECRETS_DIR` | Compose host directory, defaults to `.secrets/` |
| `FINPILOT_PORT` | Host frontend port, defaults to 3000 |
| `FINPILOT_ORIGIN` | Exact loopback frontend origins, comma separated. Change it along with the port. HTTPS origins enable Secure cookies. |
| `FINPILOT_MODE` | `development` for host runs, `container` for the authenticated proxy boundary |
| `FINPILOT_DATA_DIR` | `.finpilot/` on the host, `/data` in Compose |
| `FINPILOT_LOCAL_USER` | Server-owned ADK identity, defaults to `finpilot-local` |
| `FINPILOT_BACKEND_URL` | Next.js server only. Defaults to `http://127.0.0.1:8000` locally and `http://backend:8000` in Compose |
| `FINPILOT_REQUIRE_GEMINI` | Defaults to 1 in container mode and 0 on the host |
| `FINPILOT_PASSWORD_HASH_FILE`, `FINPILOT_SESSION_SECRET_FILE`, `FINPILOT_PROXY_SECRET_FILE`, `GOOGLE_API_KEY_FILE` | Server-only paths to secret files. Compose mounts them in `/run/secrets`. |

Local Compose secrets are individual host files mounted read-only. They
are not encrypted by Compose. The setup command keeps the host directory
private (0700) and the individual files readable by the non-root container
when mounted. Restrict host access to that directory. Use a new secret
directory to rotate credentials, then recreate the services with that
path. Rotating the signing key invalidates existing login cookies.

## Access controls and troubleshooting

- Login uses Argon2id. Five failed attempts lock the single-user password
  for ten minutes across restarts. Sessions expire after 12 hours.
  The browser uses an HttpOnly, SameSite=Strict cookie. Logout revokes it
  in SQLite. The default loopback HTTP setup intentionally omits Secure.
- Cookie-authenticated mutations require the configured request Origin
  and a session-bound CSRF token. Login also checks Origin. The backend
  has no cross-origin browser API. Generic ADK routes, OpenAPI, and
  Swagger are disabled.
- Validate a failing sign-in by checking the exact browser origin and
  configured port. If a container fails readiness, check the backend
  startup log for configuration or mount permissions. Readiness checks
  local initialization and database connectivity without calling Gemini.
- Backend logs are JSON lines with UTC time, request ID, route template,
  status, elapsed time, and a sanitized outcome. The application does
  not log statement bodies, credentials, cookies, or chat text.
  Gemini failures stream a generic user-facing error.
- Chat content renders as escaped text. Statements are size bounded,
  validated, and parsed locally. Supported Excel cells reject formulas.
  Chat inputs and selected tool results are transmitted to Gemini when
  inference is used. Stored SQLite files and backups contain sensitive
  data and are not encrypted by the app.

## Back up and recover

The scripts use SQLite's backup API to snapshot and verify each database.
They back up financial data and ADK conversations. Login sessions and
secret files are excluded. The two snapshots are individually consistent;
pause imports, budget edits, and chat if you need a common logical point
in time across both files.

For a host-run workspace:

```bash
mkdir -p backups
python -m scripts.backup_data --output backups/finpilot-snapshot
python -m scripts.restore_data --source backups/finpilot-snapshot --target .finpilot-recovered --confirm
FINPILOT_DATA_DIR="$PWD/.finpilot-recovered" uvicorn backend.main:app --port 8000
```

For a Compose workspace, take a small snapshot and copy it to private host
storage outside the volume:

```bash
umask 077
mkdir -p backups
docker compose exec -T backend python -m scripts.backup_data --output /tmp/finpilot-snapshot
docker compose cp backend:/tmp/finpilot-snapshot ./backups/finpilot-snapshot
```

The default container temporary filesystem has a 64 MiB cap. For larger
backups, provide a separate private writable backup destination instead
of using the temporary filesystem. Backups contain unencrypted statements
and conversations, so protect them at rest.

Restore into a **new** Compose project with an empty volume. Stop the
original stack before exposing recovered data on the same port. This keeps
the original volume available for rollback.

```bash
docker compose stop
tar -C backups/finpilot-snapshot -cf - transactions.sqlite3 chat_sessions.sqlite3 |
  docker compose -p finpilot-recovered run --rm --no-deps -T backend sh -ec '
    umask 077
    mkdir /tmp/backup-input
    tar -xf - -C /tmp/backup-input
    python -m scripts.restore_data --source /tmp/backup-input --target /data --confirm
  '
docker compose -p finpilot-recovered up --build -d
```

Restore first validates both database files and refuses a nonempty target,
even when `--confirm` is set. Sign in again after recovery, then confirm
the dashboard and saved conversations.

## Tests and audits

```bash
python -m unittest discover -s tests -v
python -m evaluations.run --validate
python -m evaluations.run
python -m scripts.smoke_compose
python -m pip check
pip-audit -r requirements.lock --no-deps --disable-pip
docker scout cves local://finpilot-ai-backend:latest --only-severity critical,high
docker scout cves local://finpilot-ai-frontend:latest --only-severity critical,high
cd frontend
npm ci
npm audit
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

Use `npx playwright install chromium` for the default test browser, or
`FINPILOT_BROWSER=chrome npm run test:e2e` with installed Chrome. The
browser tests start local services on ports 3000 and 8000 with disposable
secrets and SQLite files. The Compose smoke script defaults to port 3307
and uses a unique project name. It stops the test stack and keeps its
isolated synthetic volumes for inspection.

The evaluation cases use ADK's EvalSet format and the real runner with
temporary synthetic records. They check tool routing, totals, missing
records, budgets, anomaly caveats, and transfer and credential safety.
The response checks are text heuristics and may require human review.
`--validate` runs without credentials. A provider failure stops live
evaluation so later cases are reported as unverified rather than passed.

## Readiness status

| Area | Status |
| --- | --- |
| Container build and health | Locally verified on Docker Desktop Engine 29.8.0, Linux ARM64 |
| Login, proxy, uploads, budgeting, persistence | Verified using an isolated Compose project. Chat SSE returned a sanitized error without credentials, and that conversation survived restart and recreation. |
| Recovery | Verified from the running Compose backend into a distinct empty volume |
| Automated tests | 68 Python tests and 4 Chromium journeys passed. ESLint, TypeScript, and the Next.js production build passed. |
| Package audits | `npm audit` reported 0 vulnerabilities. `pip-audit -r requirements.lock --no-deps --disable-pip` found no known vulnerabilities in the pinned Python packages. |
| Image CVE scan | Both local Docker Scout commands stopped at the Docker ID login requirement. OS-level findings remain unverified. |
| Live agent evaluation | EvalSet schema validated for eight cases. The first live case received Gemini HTTP 504. Remaining cases were not executed. |
| External release | Requires TLS and identity design for the intended deployment, secrets and backup procedures, renewed image scanning, and a successful live Gemini evaluation. |

One warm run with the 24-row synthetic fixture reached both healthy
services in 12.06 seconds, including its cached build. The backend restart
reached healthy in 6.48 seconds. Import through the proxy took 12.6 ms.
Eight sequential dashboard requests had a 3.1 ms median and 4.7 ms maximum.
Docker reported image sizes of 368,539,061 bytes for the backend and
433,974,702 bytes for the frontend, with memory snapshots of 70.56 MiB and
64.48 MiB, respectively. These are local smoke measurements for a small
fixture.

Python dependencies are version-locked and npm uses `npm ci`. Container
base images pin version-series tags and digests. Refresh the locks and
digests deliberately for security updates. The single-worker model and
SQLite write limits should be revisited if the workload grows beyond a
local workspace.
