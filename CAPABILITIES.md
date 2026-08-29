# PromptForge — Current Capabilities

This file describes what PromptForge **actually does right now**. It is accurate,
not aspirational. The runtime application uses a **real local LLM via Ollama**
and contains **no fake data**.

## Status

**Working, real-LLM MVP.** The backend, Ollama provider, challenge engine, secret
detection, authentication, rate limiting, admin dashboard, security evaluation
suite, and dark-themed challenge UI are implemented and verified against a real
local `llama3.2:3b` model.

Verified:

- `28` pytest tests pass (unit tests mock only the HTTP transport)
- `ruff check app tests` passes
- `black --check app tests` passes
- `docker compose config` validates
- Alembic migration applies cleanly (`alembic upgrade head`)
- Live verification against Ollama confirmed real model responses, real latency,
  real token usage, and real solve detection

## What works today

### Real Ollama integration

- `OllamaProvider` calls the real `/api/chat` endpoint over async HTTP.
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL` are configurable; nothing is hardcoded.
- The configured model is checked against the live `/api/tags` list at health
  time. A missing model is reported as unavailable.
- Real token counts come from `prompt_eval_count` (input) and `eval_count`
  (output). If those are absent, usage is marked `available: false`, never
  approximated.
- Ollama unreachable → a clear `503` service-unavailable error; no silent
  fallback, no fabricated response.

### Core challenge loop

- Session minting, challenge listing, and attempt submission all work.
- The user prompt is sent as a separate user message; it is never interpolated
  into the system prompt.
- The hidden flag is generated at startup with `secrets.choice`.
- `SecretDetector` runs on the real model response and reports
  `challenge_solved`.

### Real latency & usage

- Latency is measured with `time.perf_counter()` around the actual Ollama call.
- Token usage is real (from Ollama) when available, otherwise `null`.
- API cost is honestly `0` (local model); local compute cost is not fabricated.

### Authentication

- Bearer tokens via `secrets.token_urlsafe`.
- SHA-256 hashes stored (not plaintext).
- Session expiry and revocation.
- Attempts associated with participant/session IDs.

### Rate limiting

- Redis-backed when `REDIS_URL` is set; explicit in-memory fallback otherwise.
- Per-participant and per-IP limits with `429` + `Retry-After`.

### Health checks

- `/health` performs real checks against FastAPI, the database, Redis (if
  configured), and Ollama (including model availability).

### Admin dashboard

- Real metrics only: participant count, attempt count, successful injections,
  success rate, average/p95 latency, error rate, and token totals (when
  available).
- A real "System status" panel (application/database/redis/ollama/model).
- Empty states are shown honestly when there is no data.

### Security evaluation

- 15 structured attack prompts.
- Results come from the real Ollama model + real `SecretDetector`.
- No hardcoded expected outcomes.
- Response is labeled `REAL MODEL EVALUATION`.

### Database & migrations

- SQLAlchemy models for participants, sessions, challenges, attempts, and usage
  metrics.
- Alembic migrations apply the real schema (`alembic upgrade head`).
- PostgreSQL in Docker; SQLite for local dev/test.

### Frontend

- Dark-themed challenge UI with real prompt/response/solve/latency/usage values.
- Separate admin dashboard with system status and real metrics.
- Token fields display "Not available" when usage is absent.

### Docker

- Multi-stage, non-root backend image.
- `docker-compose.yml` with backend + PostgreSQL + Redis.
- Ollama on the host reached via `host.docker.internal`.

### CI

- GitHub Actions workflow runs `pytest`, `ruff`, and `black --check` without
  requiring Ollama (unit tests mock the HTTP transport).

## What does not work yet

- **Local compute cost is not measured.** The dashboard shows API cost `₹0 / $0`
  but does not attempt to estimate CPU/GPU energy usage.
- **No multi-model fallback.** If the single configured model is unavailable,
  the platform reports it as unavailable rather than trying alternatives.
- **No real streaming.** Responses are returned after full completion (no
  token-by-token streaming).
- **In-memory rate limiter is per-instance.** Use Redis for cross-replica
  consistency.
- **Flag is in process memory.** Restarting the backend rotates it.

## Running

```bash
# Local (needs Ollama running)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.2:3b
uvicorn app.main:app --reload --port 8000

# Tests / lint / format
pytest -q
ruff check app tests
black --check app tests

# Docker (Postgres + Redis; Ollama on host)
docker compose up --build
```
