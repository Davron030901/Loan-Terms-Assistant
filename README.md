# Loan Terms Assistant

A scoped, grounded AI agent that answers questions about **one real bank loan contract** — with a
page number — and safely refuses everything else.

| | |
|---|---|
| **Live app** | `https://<your-app>.vercel.app` |
| **API** | `https://<your-service>.onrender.com` · [`/api/docs`](https://<your-service>.onrender.com/api/docs) |
| **Stack** | FastAPI · Google Gemini · Qdrant Cloud · Next.js 15 · Tailwind v4 |

---

## The idea

Most "AI assistants" fail because they have no job. This one has exactly one: read a bank's Terms
& Conditions and quote them. That narrowness is what makes it *checkable* — and for a money
document, checkable beats capable.

Two properties are enforced, in that order:

1. **It refuses what isn't its job.** Advice, other banks, jokes, code, prompt injections — all
   stopped at the door, before anything is even searched.
2. **It never invents a fact.** Every answer comes from the PDF and carries a page number. If the
   contract doesn't say it, the agent says `Not stated in the terms.`

```
                    ┌──────────────── VERCEL · Next.js 15 ────────────────┐
                    │  Landing · document picker · chat · live trace      │
                    │  Zero secrets. One origin: NEXT_PUBLIC_API_BASE_URL │
                    └───────────────────────┬─────────────────────────────┘
                                            │ HTTPS · POST /api/chat/stream
                                            ▼
        ┌──────────────────────── RENDER · FastAPI ────────────────────────┐
        │                                                                  │
        │  1  SCOPE GUARD ─────────► REFUSE  "I can only answer questions   │
        │     Is this even my job?           about this loan product's…"    │
        │          │ ALLOW                                                  │
        │          ▼                                                        │
        │  2  RETRIEVE   ─► Qdrant Cloud, filtered to one doc_id,           │
        │          │        top-k + relevance floor → [] means "not stated" │
        │          ▼                                                        │
        │  3  ANSWER     ─► Gemini, context-only, must emit (p. N)          │
        │          │                                                        │
        │          ▼                                                        │
        │  3b CITATION CHECK ──────► BLOCK  cited a page it never saw       │
        │          │                                                        │
        │          ▼                                                        │
        │  4  GROUNDING GUARD ─────► BLOCK  "I can't confirm this from      │
        │     Can I prove this?             the document."                  │
        │          │ GROUNDED                                               │
        │          ▼                                                        │
        │     ANSWER + CITATIONS + SOURCE CLAUSES + TRACE                   │
        └──────────────────────────────────────────────────────────────────┘
                       │                              │
                       ▼                              ▼
              Qdrant Cloud (vectors)     Google Gemini (chat + embeddings)
```

Both gates run **server-side only**. Neither can be disabled by a request parameter, and neither
exists in the browser bundle.

---

## The documents

Five real, public, text-extractable bank contracts. All five are indexed, but **exactly one is
active per conversation** — that is what keeps the scope guarantee meaningful.

| `doc_id` | Bank / Product | Pages | Chunks | Language |
|---|---|---:|---:|---|
| `cibc_personal` **(default)** | CIBC — Personal Loan Terms and Conditions (Canada) | 15 | 94 | EN |
| `cimb_personal` | CIMB — General T&C Governing Personal Loans | 13 | 73 | EN |
| `sib_personal` | The South Indian Bank — Personal Loan Agreement (India) | 7 | 72 | EN |
| `sc_vietnam` | Standard Chartered (Vietnam) — Personal Loan T&C | 10 | 60 | EN |
| `nbu_uz_green` | NBU Uzbekistan — Green Consumer Loan Contract | 5 | 24 | UZ |

Source URLs are recorded in `backend/app/data/documents.json`. The PDFs live in `backend/docs/`
and are git-ignored by default — add them yourself, or unignore them if the bank's licence allows
redistribution.

> **An honest note about these contracts.** They are *general* terms and conditions: they describe
> how interest is calculated, what counts as default, and what notice you get before a fee changes
> — but they mostly do **not** contain a fee schedule. Specific rates and dollar amounts usually
> live in a separate approval letter or disclosure statement. So `"What is the late payment fee?"`
> will often correctly return **"Not stated in the terms."** That is the system working, not
> failing, and the suggested questions in the UI are written against what these documents actually
> say.

---

## Quick start

### 1 · Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then fill in the three required values
```

Required in `.env`:

```bash
GOOGLE_API_KEY=          # Google AI Studio
QDRANT_URL=              # a free Qdrant Cloud cluster
QDRANT_API_KEY=
```

Put the five PDFs in `backend/docs/` using the exact filenames listed in `documents.json`, then
build the index **once**:

```bash
python -m scripts.ingest_all --all --recreate
# doc_id            pages  chunks  seconds
# cibc_personal        15      94      21.4
# …
```

Run it:

```bash
uvicorn app.main:app --reload
curl localhost:8000/api/health
curl localhost:8000/api/ready          # points must be > 0
```

### 2 · Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local       # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                            # http://localhost:3000
```

---

## Deployment

### Backend → Render

1. Push to GitHub. **Verify no secret is in history:**
   `git log --all --full-history -- "**/.env"` must print nothing.
2. Render → **New Web Service** → connect the repo. It reads `backend/render.yaml`.
3. Set the four `sync: false` secrets in the Render dashboard only:
   `GOOGLE_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `CORS_ORIGINS`.
4. **Ingest locally against the production cluster.** Point your local `.env` at the same
   `QDRANT_URL` and run `python -m scripts.ingest_all --all --recreate`. Keep `AUTO_INGEST=false`
   — the free tier will time out if it tries to embed a few hundred chunks during boot.

### Frontend → Vercel

1. Vercel → Import the same repo → **Root Directory: `frontend`**.
2. Environment variable, all three environments:
   `NEXT_PUBLIC_API_BASE_URL = https://<your-service>.onrender.com`
3. Deploy, then **close the CORS loop**: back in Render set
   `CORS_ORIGINS=https://<your-app>.vercel.app,http://localhost:3000`, keep
   `CORS_ORIGIN_REGEX=https://.*\.vercel\.app` so preview deploys work, and redeploy.

### Cold starts

Render's free instances sleep after ~15 minutes. The chat page pings `/api/health` on mount and
shows a *"Waking the server"* banner rather than an error, so the first request looks like a wait
instead of a crash. A free uptime pinger on `/api/health` every 10 minutes removes it entirely.

---

## How the guarantees are actually enforced

| Guarantee | Mechanism | Where |
|---|---|---|
| Off-topic never reaches the document | Regex layer (advice + injection) → LLM classifier → fail-closed parse | `app/agent/guard.py` |
| Injections cost nothing to block | 21 deterministic patterns, matched after NFKC + zero-width stripping | `guard.INJECTION_PATTERNS` |
| No answer without evidence | Relevance floor; empty retrieval returns `[]` and the writing model is never called | `app/rag/retrieve.py` |
| Page numbers are true | Chunks never cross a page boundary, so the stored page is literally where the text sits | `app/rag/chunking.py` |
| A fabricated page is caught | Cited pages are checked against the pages actually retrieved | `app/agent/citations.py` |
| A fabricated figure is caught | Every number in the draft must appear in the evidence — **no LLM call needed** | `verify.numeric_audit` |
| A subtler fabrication is caught | Independent entailment check, fresh call, temperature 0 | `app/agent/verify.py` |
| Provider failure can't leak a guess | Every guard fails **closed**: errors and timeouts mean refuse or block | `guard.py`, `verify.py` |
| Secrets never reach the browser | The frontend has exactly two `NEXT_PUBLIC_*` vars, neither a credential | `frontend/lib/api.ts` |

The single most valuable piece of code here is `numeric_audit` — about twenty lines that compare
every figure in an answer against the retrieved text. A wrong interest rate is the one failure that
actually hurts someone, and this catches it deterministically, before a token is spent.

---

## Testing

```bash
cd backend
pytest -v          # 81 tests
ruff check .
```

Highlights:

- `test_chunking.py` — for **every chunk of all five real PDFs**, asserts the text genuinely exists
  on the page it claims. If this fails, every citation is a lie.
- `test_guard.py` — advice and injection cases run with the LLM mocked to *raise*, proving the
  pattern layer resolves them without a model call.
- `test_verify.py` — the wrong-number case must be caught by `method == "numeric"`.
- `test_pipeline.py` — asserts retrieval never runs for an out-of-scope question, and that the
  answer model is never called when retrieval is empty.

### The golden test

```bash
python -m scripts.golden_test --base-url https://<your-service>.onrender.com
```

Runs 11 graded cases plus a 10-item prompt-injection corpus, writes
`backend/evidence/golden_test_results.md`, and exits `1` if any verdict is wrong.

**Then do it by hand.** Open `backend/docs/cibc_personal_loan.pdf`, find a clause with your own
eyes, note the page, and ask the agent the same thing. Record it:

| Question | Value in PDF (page) | Agent answer (page) | Match |
|---|---|---|---|
| How is interest calculated? | *fill in* (p. 4) | *fill in* | ☐ |
| What happens if a payment is late? | *fill in* (p. 5) | *fill in* | ☐ |

If a page is off by one, the PDF reader is 0-indexed somewhere — fix it before submitting.

---

## Project layout

```
backend/                      → Render
  app/
    config.py                 all env vars, validated, fail-fast
    core/  llm.py             the ONLY module that imports google.genai
           prompts.py         every prompt, versioned
           logging.py         JSON logs + X-Request-ID
           errors.py          typed errors → one JSON envelope
    rag/   chunking.py        page-aware chunker (why citations are true)
           store.py           Qdrant Cloud
           ingest.py          PDF → chunks → vectors
           retrieve.py        filtered search + relevance floor
    agent/ guard.py           ← SECURITY GATE 1
           answer.py          context-only generation
           citations.py       page validation + one repair retry
           verify.py          ← SECURITY GATE 2
           pipeline.py        the four steps, wired
    api/                      /api/chat, /api/chat/stream, /api/documents, /api/health
  scripts/  ingest_all.py · golden_test.py
  tests/    81 tests

frontend/                     → Vercel
  app/      landing · /chat · error + loading boundaries · OG image
  components/ landing/ · chat/ · ui/
  lib/      api.ts (typed client + SSE over POST) · types.ts (mirrors schemas.py)
  hooks/    useChat.ts
```

---

## Design notes

The interface exists to make the *evidence* the hero. Citations are clickable chips that open a
drawer with the exact clause and its relevance score. The trace panel shows both gates running in
real time, with latencies. Refusals and blocks are visually distinct from answers — tinted
background, coloured rail, icon — so a refusal can never be mistaken for an answer.

Violet-to-indigo brand, four semantic verdict colours (emerald / amber / rose / slate), Inter for
UI and JetBrains Mono for anything quoted from the contract. Dark and light both pass 4.5:1.
Everything animates on entry and goes completely still under `prefers-reduced-motion`. Built
mobile-first: `100dvh`, safe-area insets, 16 px inputs, 44 px tap targets, no horizontal scroll at
320 px.

---

## Limitations

- **Cold starts.** Render's free tier sleeps; the first request can take ~30 seconds.
- **No OCR.** Scanned PDFs have no text layer and will produce no chunks. All five documents here
  were verified as text-based.
- **One document per conversation.** Deliberate — cross-document answers would break the scope
  guarantee that the whole design rests on.
- **General terms, not fee schedules.** See the note above; "Not stated in the terms." is often the
  correct answer.
- **English-first.** The Uzbek NBU contract is indexed and answerable, but the guard and verifier
  prompts are tuned for English.
- **Not financial or legal advice.** This tool quotes a contract. It does not interpret it for your
  situation, and it will refuse if you ask it to.

---

## Rubric map

| Checked | Pts | Implemented in | Proven by |
|---|---:|---|---|
| Scope guard refuses off-topic and advice | 20 | `agent/guard.py` (3 layers) | `test_guard.py` · screenshots 02, 03, 08 |
| Answers use ONLY the document | 20 | `ANSWER_PROMPT` rules 1–3 + relevance floor | `test_pipeline.py` · golden test |
| Grounding guard actually blocks | 15 | `verify.numeric_audit` + LLM verifier | `test_verify.py` · screenshot 05 |
| Every answer shows a citation | 10 | `agent/citations.py` + repair retry | `test_citations.py` · screenshot 01 |
| "Not stated in the terms." | 10 | empty-retrieval path + `ANSWER_PROMPT` rule 2 | golden test · screenshot 04 |
| Real document ingested | 10 | `rag/chunking.py` → `ingest.py` → Qdrant | `/api/ready` · `test_chunking.py` |
| Working chat UI | 8 | Next.js 15 on Vercel | live URL |
| Test evidence | 4 | `backend/evidence/` | screenshots + `golden_test_results.md` |
| Clean repo | 3 | `.gitignore`, `.env.example`, this README | `git log --all -- "**/.env"` empty |

---

## Security

- `.env` is git-ignored from the first commit; only `.env.example` is tracked.
- No credential is ever sent to the browser. The frontend has two public variables, both harmless.
- PDF text is treated as untrusted data, wrapped in explicit delimiters and never as instruction.
- Questions are never persisted. Logs record a `sha256[:12]` fingerprint, not the text.
- Per-IP rate limiting, strict CORS, and security headers on every response.

**If you ever pasted a real key into a chat, an issue, or a commit — rotate it.** Assume it is
public from that moment.

---

MIT licensed. Educational project. Always read the original contract.
#   L o a n - T e r m s - A s s i s t a n t  
 