# BrandSentinel

Pre-publication brand governance (Round 1 plan, Team One-Woman Army). Checks drafts against an organisation's
approved guidelines and facts, cites the source of every finding, and leaves every decision to a human.

**Stack:** React + TypeScript + Tailwind (Vite) · FastAPI · SQLAlchemy (SQLite for dev, PostgreSQL + pgvector for production) ·
optional LLM layer · Docker.

## Run it

```bash
# dev: two terminals
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload      # API on :8000, docs at /api/docs
cd frontend && npm install && npm run dev                                            # UI on :5173, proxies /api

# one process: build the UI into backend/static, then run uvicorn only
cd frontend && npm run build && cd ../backend && uvicorn app.main:app

# docker (Postgres + pgvector + app) on :8000
docker compose up --build
```

Demo logins (password `demo123`, shown as buttons on the sign-in page): aria@ (Creator), dev@ (Creator),
leela@ (Authorised Reviewer), meera@ (Brand Manager), admin@ (Brand Admin), all `@lumora.demo`.
Set `BS_SEED_DEMO=false` and `BS_DEV_LOGIN=false` in production.

## What is implemented (mapped to the plan)

| Plan item | Where |
|---|---|
| Brand kit import; rules and facts parsed to structured records (s.5, s.18 step 1) | `kit.py` (text/md/JSON/CSV/DOCX/PDF import with preview then commit), Brand kit tab |
| Guideline management and versioning (Brand Admin) | versioned `kit_records`, history, retire, admin-only sensitive terms |
| Intake: text, HTML, DOCX, PDF with OCR, images (s.8) | `parser.py`, `images.py` |
| Detection catalogue (s.12): terminology, tone, factual accuracy, outdated info, unsupported claims, accessibility, confidentiality | `rules.py` |
| Image review: palette, contrast, clearspace, alt text | `images.py` |
| Grounded retrieval (pgvector) | `retrieval.py` (pgvector on Postgres, numpy cosine otherwise; sensitive terms never indexed) |
| AI layer with RAG restricted to approved sources, structured JSON | `ai.py` (tool-call schema, draft treated as untrusted data) |
| Control point 1, Verifier: no valid source = no finding | `verifier.py` (source exists, source type fits category, quote exists verbatim, confidence floor, de-duplication) |
| Confidence scores, "cannot verify" state | every finding; claims with no evidence record are "Cannot verify" |
| Control point 2, humans: accept, edit, dispute with reason | `services.py`, Review tab |
| Minimal-edit suggestions | glossary, facts, shouting, contrast colour fix, image palette |
| Roles, comments, routing, approvals, revision history, diffs | `services.py`, Approval and history tab |
| High-risk claim routed to Authorised Reviewer; reviewers see only high-risk items | `services.submit`, `api.full` |
| Review queue prioritised by risk | `GET /documents` |
| Append-only audit log, hash chain, verify, export | `audit.py`; Audit tab (txt, CSV, JSON) |
| AI-use log export (EU AI Act transparency) | `AIUsage` table, Audit tab |
| Local-only mode, confidential material stays local | per-draft toggle, tenant switch, auto-skip when a draft contains confidential terms |
| Governance insights: recurring mistakes, guideline-clarity score, stale-fact alerts | `insights.py`, Insights tab |
| Evaluation on 60 labelled snippets | `evalset.py`, `python -m app.evalset`, Insights tab |
| Security: RBAC, tenant isolation, encryption at rest, input sanitisation, rate limit, prompt-injection defences, OIDC | `security.py`, `db.py`, `storage.py`, `parser.py` |
| WCAG 2.2 AA target for the UI | skip link, labelled controls, keyboard-reachable highlights, tab roles, reduced motion, light and dark themes |

## AI layer

Set `ANTHROPIC_API_KEY` (and optionally `BS_LLM_MODEL`) to enable AI-assisted tone and claim checks. Without a key, or for
local-only drafts, or when a draft contains a confidential term, the model is never called and every finding is a Rule or
Heuristic. Model output goes through the same verifier as everything else. The AI path is covered by tests with an injected
fake provider; it has not been run against a live model in this build.

## Honest limits

* The 60-snippet evaluation set was written alongside the rules, so its scores (100% recall and precision) are a regression
  check, not a claim about accuracy on real content. The plan's 40% review-time reduction needs user tests; the Insights tab
  reports what is measured in your own workspace next to the survey baseline.
* PostgreSQL and pgvector, S3 storage and OIDC code paths are written but were not exercised in the build sandbox (no Postgres
  server, bucket or identity provider there). SQLite, local storage and password login are tested.
* "Tone" without an LLM is a heuristic (sarcasm phrases, shouting). Fact checks cover counts and prices; other facts are checked
  for validity dates and retired terms.

## Tests

`cd backend && pytest` (9 end-to-end API tests: RBAC, workflow routing, locking, uploads, kit versioning and import, AI grounding,
insights, audit chain, evaluation).
