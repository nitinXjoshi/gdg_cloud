# PromptForge — Adversarial LLM Sandbox

PromptForge is a **real, working prompt-injection challenge platform** that runs
against a **real local LLM via Ollama**. Participants interact with a hardened
assistant through a REST API and attempt to recover a hidden flag embedded in
the model's system prompt.

**This project uses a real local LLM through Ollama. No paid LLM API is
required.**

There is no mock provider, no fake data, and no hardcoded demo responses in the
runtime application. Every value shown by the running system originates from a
real user action, a real Ollama response, real database/Redis state, or a value
explicitly calculated from that real data.

---

## 1. Project overview

- **FastAPI** backend that orchestrates challenge attempts.
- **OllamaProvider** that talks to a local Ollama server over HTTP.
- A **hardened system prompt** containing a cryptographically random flag
  (`TVIT{...}`) generated at startup.
- A **SecretDetector** that checks the *actual* model response for flag leakage.
- Real **authentication**, **rate limiting**, **structured logging**, and
  **observability**.
- A dark-themed **challenge UI** and a separate **admin dashboard** that is
  entirely data-driven.
- A **security evaluation suite** (15 attack categories) whose results come from
  the real model.

---

## 2. Architecture

```
                    USER
                     |
                     v
              Frontend / API
                     |
                     v
                FastAPI
                     |
        +------------+------------+
        |                         |
 Authentication              Rate Limiting
        |                         |
        +------------+------------+
                     |
                     v
              Challenge Engine
                     |
                     v
              Prompt Engine
                     |
                     v
              OllamaProvider
                     |
                     v
              Ollama Server  (local)
                     |
                     v
                REAL LLM
                     |
                     v
              Real Response
                     |
          +----------+----------+
          |                     |
          v                     v
   Secret Detector         Telemetry
          |                     |
          +----------+----------+
                     |
                     v
                PostgreSQL
                     |
                     v
               Real Dashboard

Redis is used for real rate limiting (with an explicit in-memory fallback for
local dev/test).
```

```
backend/
  app/
    main.py                 # app factory + lifespan + static frontend
    api/
      routes/               # health, challenge, admin
      dependencies.py       # auth, rate-limit, admin guards
    core/
      config.py             # env-driven settings (Ollama-only)
      security.py           # tokens, hashing, constant-time compare
      logging.py            # structured JSON + redaction
      rate_limit.py         # Redis + in-memory fallback
    models/
      schemas.py            # strict Pydantic DTOs
      database.py           # async engine/session
    services/
      llm/
        base.py             # LLMProvider interface + usage types
        ollama_provider.py  # REAL Ollama HTTP client
        factory.py          # builds OllamaProvider
      challenge_engine.py   # orchestration + flag lifecycle
      prompt_engine.py      # hardened system prompt builder
      secret_detector.py    # leakage detection
      telemetry.py          # metrics computation
      attack_suite.py       # adversarial test cases (no hardcoded outcomes)
      system_status.py      # real health checks
    repositories/           # challenge/attempt persistence
    middleware/             # request ID, errors, security headers
    db/models.py            # SQLAlchemy models
  migrations/               # Alembic migrations
  tests/                    # pytest (HTTP mocked in unit tests only)
  Dockerfile
frontend/                   # vanilla JS challenge + admin UI
```

---

## 3. Ollama setup

Install Ollama and pull a model:

```bash
# macOS
brew install ollama

# Start the server
ollama serve
```

Pull a local model (recommended: `llama3.2:3b` for a good balance of quality and
local speed):

```bash
ollama pull llama3.2:3b
```

Verify it is available:

```bash
ollama list
# NAME           ID              SIZE      MODIFIED
# llama3.2:3b    a80c4f17acd5    2.0 GB    ...
```

PromptForge talks to Ollama at `OLLAMA_BASE_URL` (default
`http://localhost:11434`) using the `/api/chat` endpoint.

---

## 4. Recommended local model

`llama3.2:3b` is the default and recommended model. It runs comfortably on
consumer hardware and produces realistic refusal/extraction behavior. Any model
installed in your local Ollama can be used by setting `OLLAMA_MODEL`.

The configured model **must actually exist**. If it does not, the application
reports it as unavailable rather than pretending to be healthy.

---

## 5. Exact commands

### Backend (local, no Docker)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set your admin key (do not commit real secrets)
export ADMIN_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2:3b

uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000> (challenge) and <http://localhost:8000/admin>
(admin dashboard). Docs: <http://localhost:8000/docs>.

### Tests / lint / format

```bash
cd backend
pytest -q
ruff check app tests
black --check app tests
```

### Migrations

```bash
cd backend
# create tables from the real schema (SQLite dev default)
alembic upgrade head
```

---

## 6. Environment configuration

Copy `backend/.env.example` to `backend/.env` and edit values. Key variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_PROVIDER` | Provider (only `ollama`) | `ollama` |
| `OLLAMA_BASE_URL` | Ollama HTTP base URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Installed model name | `llama3.2:3b` |
| `DATABASE_URL` | PostgreSQL/SQLite URL | empty → SQLite |
| `REDIS_URL` | Redis URL (optional) | empty → in-memory |
| `ADMIN_API_KEY` | Admin dashboard key | generated |
| `MAX_PROMPT_LENGTH` | Max prompt chars | `12000` |
| `MAX_OUTPUT_TOKENS` | Max generation tokens | `1024` |
| `MAX_REQUESTS_PER_MINUTE` | Per-participant RPM | `20` |

Never place real secrets in `.env.example`.

---

## 7. Running backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The lifespan performs real checks: it initializes the database and builds the
Ollama provider. `/health` performs live checks against FastAPI, the database,
Redis (if configured), and Ollama.

---

## 8. Running frontend

The frontend is served statically by FastAPI at `/` and `/admin`. No separate
build step is required. To develop against a separate Vite server, set
`window.PROMPTFORGE_API_BASE` to the backend URL.

---

## 9. Docker

```bash
cp backend/.env.example .env   # set ADMIN_API_KEY and OLLAMA_MODEL
docker compose up --build
```

The backend container reaches Ollama running **on the host** via
`host.docker.internal` (configured in `docker-compose.yml` for macOS/Linux with
the host gateway). PostgreSQL and Redis run as separate containers.

If Ollama is not running, the application reports the real unavailable state —
it never falls back to fake responses.

---

## 10. API documentation

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | none | Real component status |
| POST | `/api/v1/auth/session` | none | Mint a participant session |
| GET | `/api/v1/challenges` | none | List public challenge metadata |
| GET | `/api/v1/challenges/{id}` | none | Public challenge detail |
| POST | `/api/v1/challenges/{id}/attempt` | Bearer | Run one injection attempt |
| GET | `/api/v1/stats` | none | Real aggregate stats |
| GET | `/api/v1/admin/system-status` | `X-Admin-Key` | Live component status |
| GET | `/api/v1/admin/metrics` | `X-Admin-Key` | Real dashboard metrics |
| POST | `/api/v1/admin/security/evaluate` | `X-Admin-Key` | Run real attack suite |

Attempt response:

```json
{
  "request_id": "...",
  "response": "the real model's response",
  "challenge_solved": false,
  "latency_ms": 832.4,
  "usage": {
    "available": true,
    "input_tokens": 224,
    "output_tokens": 38,
    "total_tokens": 262
  },
  "model": "llama3.2:3b"
}
```

When token usage is not reported by the model, `usage.available` is `false` and
the token fields are `null` — never fabricated.

---

## 11. Authentication

Lightweight bearer-token sessions (no OAuth):

- Tokens generated with `secrets.token_urlsafe`.
- Only SHA-256 hashes are stored.
- Sessions expire and can be revoked.
- Attempts are associated with participant/session IDs.

---

## 12. Challenge mechanics

1. At startup the backend generates a cryptographically random flag.
2. The flag is embedded in the hardened system prompt.
3. The participant's prompt is sent as a separate user message — never
   interpolated into the system prompt.
4. The prompt reaches the real Ollama model.
5. The real model response is returned to the participant.
6. `SecretDetector` checks the response for the flag.
7. The solve status and telemetry are persisted.

The only legitimate way to obtain the flag is through successful interaction
with the real model.

---

## 13. Prompt injection defense

The hardened system prompt resists direct override, system-prompt extraction,
role-play, authority impersonation, context manipulation, instruction
repetition, translation, encoding, summarization, completion, multi-turn,
indirect extraction, delimiter manipulation, debug mode, and fake system
messages.

It is deliberately **not** cryptographically secure — a prompt-injection
challenge must remain realistically attackable.

---

## 14. Secret handling

- Flag generated in memory at startup; never persisted to PostgreSQL.
- No "get flag" endpoint.
- Never logged.
- Constant-time comparison for exact detection.
- The flag is returned only in the model response when the challenge is actually
  solved.

---

## 15. Security evaluation

The admin dashboard runs a **REAL MODEL EVALUATION**: 15 adversarial prompts are
sent to the live Ollama model, the real `SecretDetector` checks each response,
and the actual results are aggregated. There are no hardcoded "this attack
succeeds/fails" outcomes.

---

## 16. Observability

- Structured JSON logs with a unique `request_id`.
- Real latency, participant/challenge IDs, provider, model, usage metadata, and
  solve status.
- Sensitive keys (secret, flag, token, API key, system prompt, credential) are
  redacted.
- Never logs the flag, system prompt, bearer tokens, or full prompts/responses.

---

## 17. Rate limiting

- Redis-backed when `REDIS_URL` is set; in-memory fallback otherwise.
- Per-participant and per-IP limits.
- `429` with `Retry-After`.

---

## 18. Known limitations

- Model quality/behavior depends on the installed Ollama model; a small model
  like `llama3.2:3b` may occasionally leak the flag even without a strong
  attack, or refuse valid benign requests. This is expected LLM behavior.
- Token usage is reported only when Ollama returns `prompt_eval_count` and
  `eval_count` (it does for `llama3.2:3b`).
- Local compute cost (CPU/GPU energy) is not measured; the dashboard shows API
  cost `₹0 / $0` and "Local compute cost not measured" where applicable.
- In-memory rate limiting is per-instance (use Redis across replicas).
- The flag is in process memory; restarting the backend rotates it.

---

## Why the LLM is NOT a security boundary

System prompts are instructions, not access control. A model given both a secret
and the ability to talk about it cannot be *guaranteed* to keep it. Prompt
injection is a behavioral problem, not a cryptographic one. PromptForge makes
that lesson measurable against a real local model.
