# DEPLOY.md — from empty accounts to a live URL

Deploying the Loan Terms Assistant: **Qdrant Cloud** (vectors) → **Render** (FastAPI) →
**Vercel** (Next.js). Everything below is on a genuinely free tier. No card required at any step.

**Total time: about 45 minutes**, most of it waiting for builds.

Follow the steps in order. Each ends with a verification you can actually run — if it doesn't pass,
stop and fix it there rather than carrying the problem forward.

---

## ⚠️ Step 0 — Rotate your keys first (5 min)

The `.env` block shared during this project contained live secrets in plain text:
`GOOGLE_API_KEY`, `OPENAI_API_KEY`, `QDRANT_API_KEY`, `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`,
`LANGFUSE_SECRET_KEY`.

**Treat every one as public. Revoke and regenerate them before you deploy.**

| Service | Where |
|---|---|
| Google AI Studio | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → delete the key → create a new one |
| Qdrant Cloud | Cluster → API Keys → revoke |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → revoke the `sk-proj-…` key |
| DeepSeek / Tavily / Langfuse | Rotate in each dashboard |

This project only needs **two** of them: `GOOGLE_API_KEY` and `QDRANT_API_KEY`. The rest belong to
the old project and can simply be revoked and forgotten.

---

## Prerequisites

| Need | Where | Cost |
|---|---|---|
| Python 3.11 | [python.org/downloads](https://www.python.org/downloads/) | Free |
| Node.js 20+ | [nodejs.org](https://nodejs.org/) | Free |
| Git + a GitHub account | [github.com](https://github.com) | Free |
| Google AI Studio key | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Free, no card |
| Qdrant Cloud account | [cloud.qdrant.io](https://cloud.qdrant.io) | Free, no card |
| Render account | [render.com](https://render.com) | Free, no card |
| Vercel account | [vercel.com](https://vercel.com) | Free, no card |

Sign in to Render and Vercel **with GitHub** — it makes the repo import one click instead of ten.

---

## Step 1 — Google Gemini key (3 min)

1. Open [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in.
2. **Create API key** → pick or create a project → copy it. It starts with `AIza…`.
3. Paste it somewhere temporary. You'll use it twice: once locally, once in Render.

This project uses two models, both on the free quota:

- `gemini-2.5-flash` — the scope guard, the answer, the verifier
- `models/gemini-embedding-001` at **768 dimensions** — ingestion and search

> **The free tier allows 100 embedding requests per minute — and the Gemini SDK sends one request
> per text**, so 323 chunks is 323 requests, not 11 batched ones. Ingestion is therefore paced at
> `EMBED_REQUESTS_PER_MINUTE=90` and takes about 4 minutes. Let it run.
>
> If it does stop on a 429, nothing is lost: each document is saved as it completes. Wait a minute
> and run `python -m scripts.ingest_all --all --resume` to pick up only what is missing.

---

## Step 2 — Qdrant Cloud cluster (5 min)

1. Go to [cloud.qdrant.io](https://cloud.qdrant.io) and sign up (GitHub or Google works).
2. **Clusters → Create** → choose the **Free** tier.
3. Pick a region **close to where you'll put Render** — e.g. `eu-central` (Frankfurt) or
   `us-east`. Every search is a round trip; a mismatched pair adds 100–200 ms to every question.
4. Wait ~2 minutes for it to go green.
5. Copy the **cluster URL** — it looks like
   `https://xxxxxxxx-xxxx-xxxx.eu-central-1-0.aws.cloud.qdrant.io`
6. **API Keys → Create** → copy the key immediately (it's shown once).

**Free tier specs:** 0.5 vCPU, 1 GB RAM, 4 GB disk — roughly one million 768-dimension vectors.
This project stores **323**. You will not come close to the ceiling.

> ### 🔴 The gotcha that will bite you at submission time
> **Free Qdrant clusters are suspended after 1 week of inactivity, and deleted after 4 weeks.**
>
> If you deploy today and your mentor opens the link in three weeks, the vector database may be
> gone and every question will return *"Not stated in the terms."*
>
> **Two defences:** log into the Qdrant dashboard once a week to keep it warm, and remember that
> re-ingesting is a one-line fix — `python -m scripts.ingest_all --all --recreate` — so keep your
> local `.env` working even after you deploy.

---

## Step 3 — Verify locally before deploying (10 min)

Never deploy something you haven't seen run. Both halves must be green here.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                # Windows: copy .env.example .env
```

Open `backend/.env` and fill in exactly three values:

```bash
OPENAI_API_KEY=sk-...                                     # primary chat provider
GOOGLE_API_KEY=AIza...                                    # chat fallback + embeddings
QDRANT_URL=https://xxxxxxxx.eu-central-1-0.aws.cloud.qdrant.io   # from Step 2
QDRANT_API_KEY=...                                        # from Step 2
```

**How the two providers are used:**

| | Provider | Fails over? |
|---|---|---|
| Chat — scope guard, answer, verifier | `CHAT_PROVIDER=openai` → `CHAT_FALLBACK_PROVIDER=gemini` | **Yes**, automatically |
| Embeddings — ingestion and search | `EMBED_PROVIDER=gemini` | **No, deliberately** |

Chat failover is safe because anything either model writes still has to pass the citation
validator and the grounding guard. A weaker fallback cannot loosen a guarantee — at worst its
answer gets blocked.

Embeddings are different. Two embedding models are two different vector spaces: a Gemini query
searched against OpenAI vectors returns numerically valid, semantically meaningless neighbours.
Retrieval would quietly become nonsense while every health check stayed green. So the embedding
provider is pinned, every stored vector is stamped with the model that produced it, and a mismatch
raises an error instead of degrading. **Changing `EMBED_PROVIDER` requires
`python -m scripts.ingest_all --all --recreate`.**

Confirm the PDFs are in place — five files, exact names:

```bash
ls docs/
# cibc_personal_loan.pdf  cimb_personal_loan.pdf  nbu_uzbek_consumer_loan.pdf
# south_indian_bank_loan.pdf  standard_chartered_loan.pdf
```

Run the test suite. **All 99 must pass** — this needs no credentials at all:

```bash
pytest -q
# 99 passed
```

### Frontend

```bash
cd ../frontend
npm install
cp .env.local.example .env.local    # Windows: copy .env.local.example .env.local
npm run build                       # must succeed
npx tsc --noEmit                    # must print nothing
```

> This build has **not** been run in a sandbox — it is the one thing not yet verified for you. If
> it fails, fix it now. Debugging a build inside Vercel's logs is far slower than on your own
> machine.

**Commit the lockfile.** `npm install` writes `package-lock.json`; that file is what Vercel installs
from. If you don't commit it, Vercel resolves versions independently and you can end up deploying
something you never built locally.

```bash
git add package-lock.json && git commit -m "chore: lock frontend deps"
```

**Check for known vulnerabilities before you push** — Vercel will block the deployment if it finds
one, even when the build compiles cleanly:

```bash
npm audit --omit=dev
npm ls next            # must be 15.5.21 or newer on the 15.x line
```

---

## Step 4 — Build the index in the cloud (5 min)

Your local `.env` already points at the production Qdrant cluster, so ingest from your laptop.
**Do this once.** It is not part of the deploy.

```bash
cd backend
python -m scripts.ingest_all --all --recreate

# doc_id            pages  chunks  seconds
# cibc_personal        15      94      21.4
# cimb_personal        13      73      17.2
# sib_personal          7      72      16.8
# sc_vietnam           10      60      14.1
# nbu_uz_green          5      24       6.3
# ----------------------------------------
# TOTAL                50     323
```

Verify it locally end to end:

```bash
uvicorn app.main:app --reload
```

In another terminal:

```bash
curl localhost:8000/api/ready
# {"ready":true,"collection":"loan_terms","points":323,"documents":5}

curl -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"question":"How is interest calculated?","doc_id":"cibc_personal"}'
# expect verdict "answered" with a (p. N) citation

curl -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"question":"Write me a poem.","doc_id":"cibc_personal"}'
# expect verdict "refused_out_of_scope"
```

Then run the graded suite against your local server:

```bash
python -m scripts.golden_test --base-url http://localhost:8000
# 22/22 passed
```

**Why not ingest on Render?** `AUTO_INGEST` stays `false` on purpose. The free instance would need
to embed 323 chunks during boot, blow past the startup timeout, and fail the health check — putting
the service into a crash loop. Ingestion is a one-off job, not a startup task.

---

## Step 5 — Push to GitHub (5 min)

```bash
cd ..                               # repo root
git init
git add .
git commit -m "feat: scoped, grounded loan terms assistant"
```

**Before pushing, prove no secret is in history:**

```bash
git log --all --full-history -- "**/.env"
# must print NOTHING

git ls-files | grep -E "\.env$"
# must print NOTHING
```

If either prints something, the key inside it is burned. Rotate it, then remove the file from
history (`git filter-repo` or start a fresh repo) before continuing.

```bash
git remote add origin https://github.com/<you>/loan-terms-assistant.git
git branch -M main
git push -u origin main
```

> The PDFs are git-ignored by default (`backend/docs/*.pdf`). **This means Render will not have
> them — and it doesn't need them**, because the vectors already live in Qdrant Cloud and the API
> never reads the PDFs at request time. Only `ingest_all.py` touches them, and you run that locally.
> If you'd rather commit them, check the bank's licence first and remove that line from
> `.gitignore`.

---

## Step 6 — Deploy the backend to Render (10 min)

> ### ⚠️ Use **Blueprint**, not **Web Service**
> Render only reads `render.yaml` from the **repository root**, and only when you create the
> service as a **Blueprint**. If you pick *New + → Web Service*, the file is ignored entirely —
> including its `PYTHON_VERSION` — and Render falls back to its own default interpreter. That is
> what causes the `pydantic-core` / maturin / "read-only file system" build failure.
>
> The repo also carries `backend/.python-version` (`3.11`), which Render honours **regardless** of
> how the service was created. Between the two, the interpreter is pinned either way.

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**.
2. Connect your GitHub repo. Render reads `render.yaml` from the repo root — root directory, build
   command, start command, health check path and the Python version all come from it.
3. Confirm what it picked up:
   - **Root Directory** `backend`
   - **Build** `pip install -r requirements.txt`
   - **Start** `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --workers 1 --timeout 120`
   - **Health Check Path** `/api/health`
   - **Instance Type** `Free`
   - **Python Version** `3.11.9`  ← check this. If it says 3.13 or 3.14, the build will fail.
4. **Environment** → add the four secrets marked `sync: false`. These live only in the dashboard:

   | Key | Value |
   |---|---|
   | `OPENAI_API_KEY` | your `sk-…` key — primary chat provider |
   | `GOOGLE_API_KEY` | your `AIza…` key — chat fallback + embeddings |
   | `QDRANT_URL` | your cluster URL |
   | `QDRANT_API_KEY` | your Qdrant key |
   | `CORS_ORIGINS` | `http://localhost:3000` *(you'll add the Vercel URL in Step 8)* |

   Everything else — `PYTHON_VERSION`, `ENVIRONMENT`, `EMBED_DIM`, `WEB_CONCURRENCY`,
   `CORS_ORIGIN_REGEX`, `AUTO_INGEST` — is already set in `render.yaml`. Don't duplicate them.

   **If you created the service as a Web Service rather than a Blueprint**, none of those defaults
   were applied. Add them all by hand, and `PYTHON_VERSION=3.11.9` first.
5. **Create Web Service.** First build takes 3–5 minutes.

### Verify

```bash
API=https://<your-service>.onrender.com

curl $API/api/health
# {"status":"ok","version":"1.0.0","environment":"production"}

curl $API/api/ready
# {"ready":true,"points":323,"documents":5,
#  "chat_providers":["openai","gemini"],"embed_provider":"gemini",
#  "embed_model":"models/gemini-embedding-001"}

curl -X POST $API/api/chat -H 'content-type: application/json' \
  -d '{"question":"How is interest calculated?","doc_id":"cibc_personal"}'
```

`/api/ready` returning `"points":0` means the API is talking to a *different* Qdrant cluster than
the one you ingested into. Compare `QDRANT_URL` character by character.

---

## Step 7 — Deploy the frontend to Vercel (5 min)

1. [vercel.com/new](https://vercel.com/new) → import the same repository.
2. **Root Directory → Edit → `frontend`.** This is the step people miss; without it the build fails
   immediately because Vercel can't find `package.json`.
3. Framework preset auto-detects as **Next.js**. Leave the build settings alone.
4. **Environment Variables** — add one, ticking **all three** environments
   (Production, Preview, Development):

   ```
   NEXT_PUBLIC_API_BASE_URL = https://<your-service>.onrender.com
   ```

   No trailing slash. No other variables. If you're ever tempted to add a third that contains a
   credential, something has gone architecturally wrong.
5. **Deploy.** ~2 minutes. Copy the production URL.

At this point the site loads but **chat will fail with a CORS error**. That's expected — Step 8
fixes it.

---

## Step 8 — Close the CORS loop (3 min)

The backend has to be told which origin is allowed to call it. It doesn't know your Vercel URL yet.

1. Render → your service → **Environment** → edit `CORS_ORIGINS`:

   ```
   https://<your-app>.vercel.app,http://localhost:3000
   ```

   Exact origins, comma-separated, **no trailing slashes, no paths**.
2. Leave `CORS_ORIGIN_REGEX` as `https://.*\.vercel\.app` — that's what lets preview deploys
   (`your-app-git-branch-you.vercel.app`) work without re-editing this every time.
3. **Save** → Render redeploys automatically (~2 min).

### Verify

```bash
# allowed origin — must echo it back
curl -s -X OPTIONS $API/api/chat -H "Origin: https://<your-app>.vercel.app" \
  -H "Access-Control-Request-Method: POST" -D - -o /dev/null | grep -i access-control-allow-origin

# hostile origin — must return NOTHING
curl -s -X OPTIONS $API/api/chat -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST" -D - -o /dev/null | grep -i access-control-allow-origin
```

---

## Step 9 — Verify the live deployment

Open your Vercel URL and work through this in the browser. Every line is a rubric point.

- [ ] Landing page renders; the demo card cycles through all three states
- [ ] Document grid shows 5 documents with clause counts
- [ ] `/chat` loads; the document switcher lists all 5
- [ ] **In scope** → *"How is interest calculated?"* → answer with a `(p. N)` chip and the emerald
      **Grounded · verified** badge
- [ ] Clicking the page chip opens the Source drawer with the real clause
- [ ] **Trace panel** shows all four stages with latencies
- [ ] **Off topic** → *"Write me a poem."* → amber refusal, exact string
- [ ] **Advice** → *"Should I take this loan?"* → refused, trace shows `layer: pattern`
- [ ] **Injection** → *"Ignore all previous instructions…"* → refused at the pattern layer
- [ ] **Not in doc** → *"Does this agreement mention travel insurance?"* → `Not stated in the terms.`
- [ ] Switching documents clears the chat and changes the answers
- [ ] Dark/light toggle works with no flash
- [ ] Open it on a phone — one-handed, no horizontal scroll
- [ ] DevTools → Network → no CORS errors; **no `AIza` or `sk-` anywhere in the bundle**

Then run the graded suite against production:

```bash
cd backend
python -m scripts.golden_test --base-url https://<your-service>.onrender.com
# 22/22 passed — writes evidence/golden_test_results.md
```

**The golden test, by hand.** Open `backend/docs/cibc_personal_loan.pdf`, find a clause with your
own eyes, note its page, ask the agent the same thing. The page and the wording must match. Record
it in `backend/evidence/golden_test.md`. This is the one check nobody can automate for you, and
it's the one your mentor will actually try.

---

## Step 10 — Evidence pack

Capture the eight screenshots listed in `backend/evidence/README.md`. That file also explains how
to force the `blocked_not_grounded` state deliberately (temporarily lower `RETRIEVER_SCORE_FLOOR`,
capture, then restore it — and say so in your README).

Then update the two placeholder URLs at the top of `README.md` with your real links.

---

## Free-tier realities

Know these before your mentor opens the link.

### Render sleeps after 15 minutes

A free web service spins down after 15 minutes without traffic and takes **about a minute** to wake.
The chat page already handles this: it pings `/api/health` on mount and shows a *"Waking the
server"* banner instead of an error.

You also get **750 free instance hours per workspace per month**. One always-on service uses ~730,
so a single service fits — but only just.

**Optional:** a free uptime pinger ([UptimeRobot](https://uptimerobot.com), [cron-job.org](https://cron-job.org))
hitting `/api/health` every 10 minutes removes cold starts entirely. The trade-off is honest —
it consumes your whole monthly hour budget, so run it in the week around your demo, not forever.

### Render's filesystem is ephemeral

Anything written to disk is lost on every deploy, restart and spin-down. This is exactly why the
vectors live in Qdrant Cloud rather than in a local `qdrant_data/` folder — embedded Qdrant would
lose the entire index on every deploy, and would also lock the directory so ingestion and the API
could never run together.

### Qdrant suspends idle free clusters after a week

Covered in Step 2, repeated because it's the one that ruins submissions. Log in weekly. If it does
get suspended, reactivate it in the dashboard and re-run `ingest_all` if the data is gone.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Vercel build fails, "no package.json" | Root Directory not set | Project Settings → General → Root Directory → `frontend` |
| **"Vulnerable version of Next.js detected"** — build compiles fine, deployment still fails | Vercel blocks any deployment containing a Next.js version affected by CVE-2025-66478 (RSC stream cross-session injection) | Upgrade. `package.json` pins `next@^15.5.21`; run `npm install`, commit the updated `package-lock.json`, push. Do **not** use the `DANGEROUSLY_DEPLOY_VULNERABLE_CVE_2025_66478` escape hatch — the vulnerability is real |
| `npm install` resolves an old Next.js anyway | A stale `package-lock.json` is committed | `rm -rf node_modules package-lock.json && npm install`, then commit the new lockfile |
| Every question returns "Not stated in the terms." | API pointing at the wrong cluster, or the index is empty | `curl $API/api/ready` — if `points: 0`, re-check `QDRANT_URL` and re-run `ingest_all` |
| CORS error in the browser console | Vercel URL missing from `CORS_ORIGINS` | Add the exact origin (no trailing slash), redeploy Render |
| First request takes ~60 s | Render cold start | Expected. The waking banner covers it; add an uptime pinger if you want it gone |
| `/api/ready` returns 503 | Collection empty or Qdrant unreachable | Check the Qdrant dashboard — the cluster may be suspended |
| **Build fails: `pydantic-core` … `maturin failed` … `Read-only file system`** | Render is on Python 3.13/3.14, which has no prebuilt wheel for the pinned `pydantic-core`, so pip tries to compile it from Rust source — and the cargo cache dir is read-only | Pin the interpreter. Render → Environment → `PYTHON_VERSION=3.11.9` → **Manual Deploy → Clear build cache & deploy**. Check the log's first lines say `python3.11`. The repo's `backend/.python-version` does this automatically on a fresh deploy |
| Build log shows `--interpreter …/bin/python3.14` | `render.yaml` was ignored — it only applies to services created as a **Blueprint**, from the **repo root** | Set `PYTHON_VERSION` manually, or delete the service and recreate it via New + → Blueprint |
| Any `error: metadata-generation-failed` on a pinned package | An exact pin with no wheel for the host interpreter | `requirements.txt` now uses version *ranges* for exactly this reason. Pull the latest `main` |
| Service crash-loops on boot | `AUTO_INGEST=true` | Set it to `false`. Never ingest during startup on the free tier |
| `Vector dimension error` on ingest | Collection built at a different size | `python -m scripts.ingest_all --all --recreate` with `EMBED_DIM=768` |
| 429 from Gemini during ingest | Free-tier per-minute limit | Harmless — tenacity retries with backoff. Let it run |
| **Every question is refused, including obviously valid ones** | `gemini-2.5-*` are thinking models: hidden reasoning tokens come out of the same `max_output_tokens` budget, so a short budget returns empty text — and a fail-closed guard reads empty as REFUSE | Fixed in code: `GEMINI_DISABLE_THINKING=true` and `VERDICT_MAX_TOKENS=32`. Look for `scope_guard_no_verdict` in the logs |
| **Answers take 15–25 seconds** | The primary chat provider is failing, and each question makes three chat calls — so the failover penalty was paid three times | Fixed by the circuit breaker: a failed provider is skipped for 60 s. Check `curl $API/api/ready` → `provider_health` |
| `llm_provider_failed` … `"Cannot send a request, as the client has been closed."` | The cached SDK client's transport died between calls — the pipeline runs in worker threads and the SDK tears its transport down with its internal event loop | Fixed in code: the client is rebuilt and the call retried. Look for `llm_client_rebuilt` |
| `llm_provider_failed` with `"fatal": true` | The key is revoked, wrong, or out of credit — not a transient outage | Replace the key, or set `CHAT_PROVIDER=gemini` and `CHAT_FALLBACK_PROVIDER=none` |
| Ingestion dies partway with `429 RESOURCE_EXHAUSTED` | The free tier's per-minute embedding ceiling | Wait 60 s, then `python -m scripts.ingest_all --all --resume`. Completed documents are kept |
| `curl` behaves strangely on Windows | PowerShell aliases `curl` to `Invoke-WebRequest` | Use `curl.exe` or `Invoke-RestMethod` |
| Answers still work after OpenAI billing lapses | Chat failed over to Gemini — check the logs for `llm_provider_failed` | Working as designed. `/api/ready` shows the active chain |
| `RetrievalError: The index was built with '…' but EMBED_PROVIDER now resolves to '…'` | You changed the embedding provider without re-indexing | `python -m scripts.ingest_all --all --recreate` |
| Every answer is wrong but nothing errors | Almost certainly a mixed vector space | `curl $API/api/ready` and compare `embed_model` against what you ingested with |
| Answers arrive but with no citations | Model ignoring the format | Check `LLM_TEMPERATURE=0`; the citation validator will block these rather than show them |
| Guard refuses a legitimate question | A pattern is too broad | Add the case to `tests/test_guard.py`, then narrow the regex in `guard.py` |

---

## Redeploying after a change

Both platforms deploy on push to `main`:

```bash
git add .
git commit -m "fix: ..."
git push
```

Render rebuilds (~3 min), Vercel rebuilds (~2 min). Neither touches Qdrant.

**Re-run ingestion only when you change the PDFs, the chunker, or `EMBED_DIM`:**

```bash
cd backend && python -m scripts.ingest_all --all --recreate
```

**Rollback:** Vercel → Deployments → any previous build → **Promote to Production** (instant).
Render → Events → **Rollback** to a previous deploy.

---

## The final check

```bash
curl https://<your-service>.onrender.com/api/ready
# {"ready":true,...,"points":323,"documents":5}

python -m scripts.golden_test --base-url https://<your-service>.onrender.com
# 22/22 passed
```

Green on both, plus the hand-verified golden test, and you're done.

---

## Why the pins are ranges

`requirements.txt` uses `>=x,<y` rather than `==x.y.z`. That is deliberate.

An exact pin is only reproducible if a prebuilt wheel exists for the interpreter you land on. When
Render moved its default Python forward, `pydantic-core==2.27.2` had no matching wheel, so pip fell
back to building it from Rust source — which fails on a read-only cargo cache. Ranges let pip pick
a version that actually has a wheel.

The suite is verified green across Python 3.10–3.13 and against the newest release in every range
(pydantic 2.13, fastapi 0.141, pypdf 6.13): **99/99 passed**.

---

**Sources:** [Render — Deploy for Free](https://render.com/docs/free) ·
[Qdrant — Creating a Cloud Cluster](https://qdrant.tech/documentation/cloud/create-cluster/) ·
[Qdrant — Pricing](https://qdrant.tech/pricing/)
