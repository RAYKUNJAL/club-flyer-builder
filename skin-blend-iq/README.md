# Skin Blend IQ

AI skin-tone capture, pigment calibration, and drop-formula platform for trained
tattoo and paramedical tattoo practitioners — built from the
*Skin Blend IQ Complete App Master Spec v3*.

> **Skin Blend IQ is an artist decision-support system.** It does not diagnose,
> does not determine medical suitability, and does not guarantee healed color.
> Treatment-grade output requires calibrated capture, measured pigment data,
> whole-drop quantization, an external swatch, and artist approval.

## Architecture

```
skin-blend-iq/
├── backend/          Python FastAPI + SQLAlchemy (SQLite by default, Postgres-ready)
│   ├── app/
│   │   ├── colorscience/   sRGB↔XYZ↔CIE L*a*b* (D65/2°), CIEDE2000 & ΔE76,
│   │   │                   reference-card correction, image quality scoring
│   │   ├── formula/        measured-mixture model, constrained solver,
│   │   │                   sum-preserving whole-drop quantization, mL/fl-oz scaling
│   │   └── routers/        /v1 REST API (auth, clients, captures, pigments,
│   │                       formulas, sessions, audit, reports)
│   └── tests/        122 pytest tests (see "Validation")
└── frontend/         React 18 + TypeScript (Vite) SPA, served by the backend
```

## Quick start

```bash
# Backend
cd skin-blend-iq/backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# Frontend
cd ../frontend
npm install && npm run build

# Run (serves API + built frontend on :8000)
cd ../backend
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — a demo studio is seeded:
`demo@skinblendiq.test` / `demo-password-123`, including the five-pigment
**synthetic demo kit** (P-Y, P-R, P-B, P-W, P-K). Synthetic-kit formulas are
watermarked *not treatment-grade* and are hard-blocked from test spots and
treatment sessions (spec Appendix B, warning 1).

Config via env vars: `SBI_DATABASE_URL` (any SQLAlchemy URL — point at Postgres
in production), `SBI_JWT_SECRET`, `SBI_UPLOAD_DIR`, `SBI_FRONTEND_DIST`.

### Run the tests

```bash
cd skin-blend-iq/backend
./.venv/bin/python -m pytest tests/ -q      # 122 tests
```

## What is implemented (spec coverage)

**Deterministic color pipeline (spec §7):** embedded-value → sRGB → linear →
XYZ → CIE L*a*b* under declared D65/2°; CIEDE2000 validated against 29
Sharma–Wu–Dalal reference pairs; ΔE76 stored for debugging; chroma/hue, HSV,
ITA°, undertone classifier with confidence.

**Calibrated capture (§6):** reference-card definitions; per-image quality
scoring (focus via Laplacian variance, over/under-exposure, glare, resolution)
with pass/marginal/fail grades; least-squares color correction fitted from
artist-marked card patches with stored residual; multi-patch skin sampling
using medians and robust spread; patch rejection reasons (glare, shadow, hair,
redness, scar tissue, …); treatment-grade gates: calibrated mode + ≥3 passing
images + passing corrections + ≥3 patches + variation tolerance. Quick/manual
entries are never treatment-grade; instrument entries are.

**Pigments & calibration (§8–9):** products, lot tracking with expiry,
dropper calibration records with tolerance warnings, kits with versioned
datasets flagged `measured` or `synthetic`, measured mixture-sample library
(pure pigments, binary ladders, ternaries).

**Formula engine (§10–11):** nearest-neighbor + local-interpolation mixture
model over measured samples; deterministic constrained solver on the simplex
(exclusions, locked pigments, max pigments); gamut assessment;
largest-remainder whole-drop quantization that always totals exactly
(10/20/40/custom) with no negatives; predicted color **recalculated after
rounding** and the added rounding ΔE disclosed; master continuous ratio kept
in the audit trail; ranked alternatives; confidence score.

**Safety controls (§3, §12, §19):** recalled/expired/quarantined/depleted lots
blocked at generation, re-verified at lock and batch time; external swatch
verification mandatory before approval; approval requires the professional
acknowledgment and artist+ role; locked formulas are immutable (changes create
a new version); synthetic-data and non-calibrated formulas are hard-blocked
from any treatment endpoint; test-spot approval (or documented senior
override) gates full sessions; treatment consent required and consent kinds
(treatment/photography/education/marketing/AI-training) are recorded
separately; senior follow-up review with AI-training consent check before any
learning eligibility; no automatic online learning.

**Practice OS (v3 expansion, core subset):** client records with display
codes, cases with the full status ladder, body zones with status layers,
formula scaling to mL and US fluid-ounce presets preserving exact total volume
with disclosed rounding differences, batch preparation with printed label text
and inventory deduction, batch usage/discard tracking, coverage estimator,
configurable pricing estimator with area tiers, test-spot workflow with healed
review checklist, adverse-event reports, recall → affected-client search.

**Platform (§15–18):** multi-tenant with enforced isolation (verified by
tests), JWT auth + roles (owner/senior/artist/trainee), hash-chained immutable
audit log with tamper detection and a verify endpoint, PDF formula report,
model + dataset versions recorded on every formula.

## Validation (spec §20–21)

- `tests/test_colorscience.py` — conversion round-trips, known values, 29
  CIEDE2000 reference pairs to 1e-4.
- `tests/test_engine.py` — quantization exactness & determinism, exact-volume
  scaling (including the spec's ½-oz example), correction recovery of a known
  cast, quality-gate behavior, and the §21 proof-of-concept assertions (exact
  20/40-drop totals, no negatives, four target classes, color recalculated
  after rounding).
- `tests/test_api_workflow.py` — full lifecycle over the API, including
  calibrated capture with synthetic photos recovering the true skin color.
- `tests/test_safety.py` — every safety block above.
- `tests/test_tenancy_audit.py` — tenant isolation, audit chain, tamper
  detection.

A live end-to-end script (52 checks) and Playwright browser runs were used to
verify the running server and UI during development.

## Deliberate scope notes

- **SQLite default, Postgres-ready:** models use portable SQLAlchemy types;
  set `SBI_DATABASE_URL` for PostgreSQL in production.
- **Vite + React SPA** instead of Next.js: same React/TypeScript component
  model, single-container deployment; swappable later without API changes.
- Later-release items from the spec (native camera modules, spectrophotometer
  integration, ML segmentation, healed-color prediction, scheduling/forms
  builder/payments, offline sync, white-label) are not part of this MVP build,
  matching the spec's phased roadmap.
