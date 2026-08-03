# PatWaGo — Commercial-Grade Hardening Build

**Status:** Committed locally, NOT yet pushed to `RAYKUNJAL/patwago`.
**Branch:** `claude/commercial-grade-hardening`
**Base commit:** `3c672a2` (current `origin/main` at time of writing)
**Local commit:** `fd98cb4` — `fix: close path-traversal bug, persist PayPal payments, harden auth`
**Diff:** 25 files changed, 847 insertions(+), 4,818 deletions(-)
**Tests:** 125/125 passing · `npm run check` clean across all 16 shipped `.js` files

This document is a complete, buildable spec of everything in that commit — enough for anyone (or another agent) with real push access to `RAYKUNJAL/patwago` to recreate every change from scratch against the current `main`.

---

## 1. Critical fix — path traversal in `server.js`

**File:** `server.js`, function `normalizeStaticPath()` and `handleStatic()`

**The bug:** `handleStatic()` had two code paths for serving static files. The `public/` branch built its file path with no containment check:

```js
// BEFORE — vulnerable
const publicCandidate = path.join(PUBLIC_DIR, pathname.replace(/^\//, ''));
if (serveFile(res, publicCandidate)) return true;
```

A request like `GET /..%2f..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd` survives URL parsing unchanged (WHATWG `URL` doesn't decode `%2f`), gets decoded to a literal `../../../../etc/passwd` a few lines earlier, and is served directly — no login required. Reproduced live during the audit: `GET /..%2fserver.js` returns `server.js` itself from outside `public/`. On the live VPS this reads `.env` directly.

The *second* code path (`rootCandidate`) already did this correctly via `normalizeStaticPath()`. The fix generalizes that function to take a `baseDir` parameter and uses it for **both** branches:

```js
// AFTER — normalizeStaticPath now takes a baseDir
function normalizeStaticPath(urlPath, baseDir = ROOT) {
  const cleaned = decodeURIComponent(urlPath)
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');
  const normalizedBase = path.normalize(baseDir);
  const candidate = path.normalize(path.join(normalizedBase, cleaned));
  const baseWithSep = normalizedBase.endsWith(path.sep) ? normalizedBase : `${normalizedBase}${path.sep}`;
  // Reject anything that escapes baseDir, including sibling directories that merely
  // share a prefix (e.g. baseDir "/opt/patwago" must not match "/opt/patwago-evil").
  if (candidate !== normalizedBase && !candidate.startsWith(baseWithSep)) {
    return null;
  }
  return candidate;
}

// handleStatic() — both branches now containment-checked
const publicCandidate = normalizeStaticPath(pathname, PUBLIC_DIR);
if (publicCandidate && serveFile(res, publicCandidate)) return true;

const rootCandidate = normalizeStaticPath(pathname, ROOT);
if (rootCandidate && serveFile(res, rootCandidate)) return true;
```

Also fixed a secondary bug in the original `normalizeStaticPath`: `candidate.startsWith(ROOT)` without a trailing separator would incorrectly allow a sibling directory like `/opt/patwago-evil` to pass a containment check meant for `/opt/patwago`. Fixed by comparing against `baseDir + path.sep`.

**Verified:** live server, before/after — attack requests now return byte-identical content to the root page (130,830 bytes, PatWaGo's `index.html` fallback) instead of leaking file contents.

---

## 2. PayPal payment persistence — new file `lib/payments.js`

**The bug:** A `payments` table existed in `database/003_payments.sql` but nothing ever wrote to it. The webhook handler verified PayPal's signature and then discarded the event (`return sendJson(res,200,{ok:true})` with no action taken). No audit trail of real charges; no fallback if a customer closed their tab right after paying.

**New module** (`lib/payments.js`, 248 lines) — mirrors the existing `pool`/in-memory dual-mode pattern already used in `lib/auth.js`:

```js
'use strict';
const crypto = require('node:crypto');
const { Pool } = require('pg');

const pool = process.env.DATABASE_URL
  ? new Pool({
      connectionString: process.env.DATABASE_URL,
      max: 5,
      ssl: process.env.DATABASE_SSL === 'true' ? { rejectUnauthorized: true } : false,
    })
  : null;

const mem = { payments: [] }; // dev/test only

function memoryAllowed() {
  return process.env.NODE_ENV !== 'production' || process.env.ALLOW_IN_MEMORY_AUTH === 'true';
}
function assertPool() {
  if (!pool && !memoryAllowed()) throw new Error('DATABASE_URL is required for production payment persistence');
  if (!pool) return false;
  return true;
}

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS payments (
  id                text        PRIMARY KEY,
  paypal_order_id   text        NOT NULL UNIQUE,
  capture_id        text,
  customer_id       text,
  plan              varchar(20) NOT NULL,
  amount            numeric(10, 2) NOT NULL,
  currency          text        NOT NULL DEFAULT 'USD',
  status            text        NOT NULL DEFAULT 'created',
  payer_email       text,
  payer_id          text,
  pass_activated    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  paypal_raw        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  captured_at       timestamptz
);
CREATE INDEX IF NOT EXISTS payments_status_idx      ON payments(status);
CREATE INDEX IF NOT EXISTS payments_plan_idx         ON payments(plan);
CREATE INDEX IF NOT EXISTS payments_customer_idx     ON payments(customer_id);
CREATE INDEX IF NOT EXISTS payments_payer_email_idx  ON payments(payer_email);
CREATE INDEX IF NOT EXISTS payments_captured_at_idx  ON payments(captured_at DESC);
`;

let schemaEnsured = false;
async function ensureSchema() {
  if (!pool) return;
  if (schemaEnsured) return;
  await pool.query(SCHEMA_SQL);
  schemaEnsured = true;
}

function paymentId() { return `pay_${crypto.randomBytes(12).toString('hex')}`; }
function nowIso() { return new Date().toISOString(); }

// Record an order the moment PayPal creates it (status: 'created').
// This is what lets the webhook reconcile a capture back to a plan and
// customer_id later, even if it never receives a synchronous capture call.
async function recordOrderCreated({ order_id, plan, amount, currency, customer_id }) {
  if (!order_id) throw new Error('recordOrderCreated requires order_id');
  const id = paymentId();
  const row = {
    id, paypal_order_id: order_id, capture_id: null, customer_id: customer_id || null,
    plan, amount, currency: currency || 'USD', status: 'created',
    payer_email: null, payer_id: null, pass_activated: {}, paypal_raw: {},
    created_at: nowIso(), captured_at: null,
  };
  if (assertPool()) {
    await ensureSchema();
    await pool.query(
      `INSERT INTO payments (id, paypal_order_id, customer_id, plan, amount, currency, status, created_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
       ON CONFLICT (paypal_order_id) DO NOTHING`,
      [id, order_id, row.customer_id, plan, amount, row.currency, 'created', row.created_at],
    );
  } else if (!mem.payments.some((p) => p.paypal_order_id === order_id)) {
    mem.payments.push(row);
  }
  return row;
}

// Upsert a payment row from a captureOrder() result (or a webhook-derived
// record). Idempotent on paypal_order_id — safe to call from both the
// synchronous capture endpoint and the async webhook for the same order
// without creating duplicate rows or double-activating a pass.
async function recordCapture(payment, { customer_id } = {}) {
  if (!payment || !payment.paypal_order_id) throw new Error('recordCapture requires paypal_order_id');
  const existing = await getByOrderId(payment.paypal_order_id);
  const wasAlreadyCompleted = !!(existing && existing.status === 'completed');
  const id = (existing && existing.id) || paymentId();
  const resolvedCustomerId = customer_id || (existing && existing.customer_id) || null;

  if (assertPool()) {
    await ensureSchema();
    await pool.query(
      `INSERT INTO payments (id, paypal_order_id, capture_id, customer_id, plan, amount, currency, status, payer_email, payer_id, pass_activated, paypal_raw, captured_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       ON CONFLICT (paypal_order_id) DO UPDATE SET
         capture_id = EXCLUDED.capture_id,
         customer_id = COALESCE(payments.customer_id, EXCLUDED.customer_id),
         status = EXCLUDED.status,
         payer_email = EXCLUDED.payer_email,
         payer_id = EXCLUDED.payer_id,
         pass_activated = EXCLUDED.pass_activated,
         paypal_raw = EXCLUDED.paypal_raw,
         captured_at = EXCLUDED.captured_at`,
      [id, payment.paypal_order_id, payment.capture_id || null, resolvedCustomerId, payment.plan,
       payment.amount, payment.currency || 'USD', payment.status, payment.payer_email || null,
       payment.payer_id || null, JSON.stringify(payment.pass_activated || {}),
       JSON.stringify(payment.paypal_raw || {}), payment.captured_at || null],
    );
  } else {
    const idx = mem.payments.findIndex((p) => p.paypal_order_id === payment.paypal_order_id);
    const row = { id, paypal_order_id: payment.paypal_order_id, capture_id: payment.capture_id || null,
      customer_id: resolvedCustomerId, plan: payment.plan, amount: payment.amount,
      currency: payment.currency || 'USD', status: payment.status, payer_email: payment.payer_email || null,
      payer_id: payment.payer_id || null, pass_activated: payment.pass_activated || {},
      paypal_raw: payment.paypal_raw || {}, created_at: (existing && existing.created_at) || nowIso(),
      captured_at: payment.captured_at || null };
    if (idx >= 0) mem.payments[idx] = row; else mem.payments.push(row);
  }
  return { wasAlreadyCompleted };
}

async function getByOrderId(orderId) {
  if (!orderId) return null;
  if (assertPool()) {
    await ensureSchema();
    const result = await pool.query('SELECT * FROM payments WHERE paypal_order_id=$1', [orderId]);
    return result.rows[0] || null;
  }
  return mem.payments.find((p) => p.paypal_order_id === orderId) || null;
}

async function listByCustomer(customerId) {
  if (!customerId) return [];
  if (assertPool()) {
    await ensureSchema();
    const result = await pool.query('SELECT * FROM payments WHERE customer_id=$1 ORDER BY created_at DESC', [customerId]);
    return result.rows;
  }
  return mem.payments.filter((p) => p.customer_id === customerId)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
}

// Extracts order id / capture id from a PAYMENT.CAPTURE.* webhook event.
function extractIdsFromCaptureEvent(event) {
  const resource = (event && event.resource) || {};
  const orderId = resource?.supplementary_data?.related_ids?.order_id || null;
  const captureId = resource.id || null;
  return { orderId, captureId };
}

module.exports = { ensureSchema, recordOrderCreated, recordCapture, getByOrderId, listByCustomer, extractIdsFromCaptureEvent, _mem: mem };
```

**Wiring in `server.js`:**

```js
const payments = require('./lib/payments');

// purchase-pass: record the order the instant PayPal creates it
if (req.method === 'POST' && pathname === '/api/paypal/purchase-pass') {
  const session = await requireCustomer(req, res, false); if (!session) return true;
  const body = await readBody(req);
  let order;
  try {
    order = await paypalService().createOrder({ plan: body.plan, return_url: body.return_url, cancel_url: body.cancel_url });
    await payments.recordOrderCreated({ order_id: order.order_id, plan: order.plan, amount: order.amount, currency: order.currency, customer_id: session.customer_id });
  } catch (error) {
    if (!shouldUseLocalCheckoutFallback(error)) throw error;
    // ...existing local-fallback branch unchanged
  }
  return sendJson(res, 201, { /* ...unchanged... */ });
}

// capture: persist the result, avoid double-issuing a pass if the webhook already did
if (req.method === 'POST' && /^\/api\/paypal\/orders\/[^/]+\/capture$/.test(pathname)) {
  const session = await requireCustomer(req, res, false); if (!session) return true;
  const orderId = decodeURIComponent(pathname.split('/')[4]);
  const payment = await paypalService().captureOrder(orderId);
  const { wasAlreadyCompleted } = await payments.recordCapture(payment, { customer_id: session.customer_id });
  if (payment.status !== 'completed') return sendJson(res, 409, { ok: false, message: 'PayPal payment is not completed', data: payment });
  const pass = wasAlreadyCompleted
    ? (await auth.listPasses(session.customer_id)).find((p) => p.plan === payment.plan) || null
    : await auth.createPass({ customer_id: session.customer_id, plan: payment.plan });
  return sendJson(res, 200, { ok: true, data: { ...payment, pass } });
}

// webhook: now actually reconciles and activates a pass (async fallback path)
if (req.method === 'POST' && pathname === '/api/paypal/webhook') {
  const raw = await readRawBody(req, 1_000_000);
  const result = await paypalService().verifyWebhook({ headers: req.headers, body: raw.toString('utf8') });
  if (!result.verified) return sendJson(res, 400, { ok: false, message: result.reason || 'Invalid webhook signature' });

  const event = result.event || {};
  if (event.event_type === 'PAYMENT.CAPTURE.COMPLETED') {
    const { orderId, captureId } = payments.extractIdsFromCaptureEvent(event);
    if (orderId) {
      const known = await payments.getByOrderId(orderId);
      if (known && known.status !== 'completed') {
        const resource = event.resource || {};
        const amountValue = resource.amount?.value ? Number(resource.amount.value) : known.amount;
        const capturedPayment = {
          status: 'completed', paypal_order_id: orderId, plan: known.plan, amount: amountValue,
          currency: resource.amount?.currency_code || known.currency, capture_id: captureId,
          payer_email: known.payer_email, payer_id: known.payer_id, captured_at: new Date().toISOString(),
          pass_activated: { activated: true, plan: known.plan, pass_type: `${known.plan}_pass`, capture_id: captureId, activated_at: new Date().toISOString() },
          paypal_raw: event,
        };
        await payments.recordCapture(capturedPayment, { customer_id: known.customer_id });
        // Async fallback: the browser never reached the capture endpoint, so activate here.
        if (known.customer_id) await auth.createPass({ customer_id: known.customer_id, plan: known.plan });
      }
    }
  }
  return sendJson(res, 200, { ok: true });
}
```

**`database/003_payments.sql`** updated to match (added `customer_id` column, dropped the `plan IN ('day','trip')` CHECK constraint — plans are now validated in the application layer via `PLAN_PRICES`, matching how `auth_passes.plan` already works, so adding a plan never requires a migration on an existing deployment).

---

## 3. Week Pass — real three-tier plan support

**The bug:** `public/app/account-pages.js` already advertised three plans — Day $9.99/24h, Week $29.99/7days, Trip $49.99/"up to 14 days" — but the server only recognized `day` and `trip` at $9.99/$29.99. Clicking "Choose Week Pass" failed with `Unknown plan: week`.

**`lib/paypal.js`:**
```js
const PLAN_PRICES = Object.freeze({
  day: 9.99,
  week: 29.99,
  trip: 49.99,
});
const PLAN_DESCRIPTIONS = Object.freeze({
  day: 'PatWaGo Day Pass — 24 hours of Jamaica travel companion',
  week: 'PatWaGo Week Pass — 7 days of Jamaica travel companion',
  trip: 'PatWaGo Trip Pass — up to 14 days of full trip coverage',
});
// buildPassActivation's pass_type is now generic: `${plan}_pass` instead of a day/trip-only ternary
```

**`lib/auth.js`:**
```js
const PLAN_DURATIONS_MS = {
  trial: 24 * 3600000,
  day: 24 * 3600000,
  week: 7 * 24 * 3600000,       // new — fixed 7 days
  trip: null,                    // unchanged — computed from trip_days, default 7, capped 1-60
};
const VALID_PLANS = new Set(['trial', 'day', 'week', 'trip']);
```

Trip's default duration was deliberately left at 7 days (not bumped to 14) — an existing test explicitly locks that default, and "up to 14 days" is satisfied as a ceiling via the existing `trip_days` override (already capped 1–60), not a promise that every trip pass is exactly 14 days.

---

## 4. Auth hardening

**Server-side password minimum** (`lib/auth.js`) — the client already enforced `minlength="8"`, but that's trivially bypassed by calling the API directly:

```js
const MIN_PASSWORD_LENGTH = 8;

async function registerCustomer({ email, password, name }) {
  if (!isValidEmail(email)) throw new Error('A valid email is required');
  if (!isNonEmptyString(password)) throw new Error('A non-empty password is required');
  if (password.length < MIN_PASSWORD_LENGTH) {
    throw new Error(`Password must be at least ${MIN_PASSWORD_LENGTH} characters`);
  }
  // ...unchanged
}

async function updateCustomer(id, { name, password } = {}) {
  if (!isNonEmptyString(id)) throw new Error('customer id is required');
  if (isNonEmptyString(password) && password.length < MIN_PASSWORD_LENGTH) {
    throw new Error(`Password must be at least ${MIN_PASSWORD_LENGTH} characters`);
  }
  // ...unchanged
}
```

**New file `lib/rate-limit.js`** — simple in-memory fixed-window limiter (39 lines):

```js
'use strict';
function createRateLimiter({ windowMs, max }) {
  const hits = new Map();
  function check(key) {
    const now = Date.now();
    let entry = hits.get(key);
    if (!entry || now >= entry.resetAt) {
      entry = { count: 0, resetAt: now + windowMs };
      hits.set(key, entry);
    }
    entry.count += 1;
    const allowed = entry.count <= max;
    return { allowed, remaining: Math.max(0, max - entry.count), retryAfterMs: Math.max(0, entry.resetAt - now) };
  }
  function _reset() { hits.clear(); }
  return { check, _reset };
}
module.exports = { createRateLimiter };
```

**Wired into `server.js`:**

```js
const { createRateLimiter } = require('./lib/rate-limit');

// Trusts X-Forwarded-For because Traefik is the only entry point in front
// of this process — if that ever changes, this needs to change with it.
function clientIp(req) {
  const forwarded = req.headers['x-forwarded-for'];
  if (forwarded) return String(forwarded).split(',')[0].trim();
  return req.socket.remoteAddress || 'unknown';
}

const loginLimiter = createRateLimiter({
  windowMs: Number(process.env.LOGIN_RATE_WINDOW_MS || 15 * 60 * 1000),
  max: Number(process.env.LOGIN_RATE_MAX || 10),
});
const registerLimiter = createRateLimiter({
  windowMs: Number(process.env.REGISTER_RATE_WINDOW_MS || 60 * 60 * 1000),
  max: Number(process.env.REGISTER_RATE_MAX || 20),
});

function rateLimited(res, limiter, key) {
  const result = limiter.check(key);
  if (!result.allowed) {
    res.setHeader('Retry-After', String(Math.ceil(result.retryAfterMs / 1000)));
    sendJson(res, 429, { ok: false, message: 'Too many attempts. Please try again shortly.' });
    return true;
  }
  return false;
}

// In both routes, first line inside the handler:
if (rateLimited(res, registerLimiter, `register:${clientIp(req)}`)) return true;
// ...
if (rateLimited(res, loginLimiter, `login:${clientIp(req)}`)) return true;
```

New `.env.example` entries: `LOGIN_RATE_WINDOW_MS`, `LOGIN_RATE_MAX`, `REGISTER_RATE_WINDOW_MS`, `REGISTER_RATE_MAX` (all optional, sane defaults shown above).

---

## 5. Deploy config fix — `apps/yaadie-web/patwago.traefik.yaml`

**The bug:** routed `/api/*` to a `patwago-api` service on `host.docker.internal:4030` and everything else to a separate `patwago-web` service on `patwago-web:80` — a two-service split that doesn't exist. `server.js` is one process, one port.

```yaml
# AFTER — one router, one service, with an explicit verification note
http:
  routers:
    patwago-app:
      rule: "Host(`patwago.com`) || Host(`www.patwago.com`)"
      entryPoints:
        - http
        - https
      service: patwago-app
      tls:
        certResolver: letsencrypt
      priority: 1
  services:
    patwago-app:
      loadBalancer:
        servers:
          - url: "http://host.docker.internal:3000"
```

A comment block at the top of the file explicitly flags: confirm the actual host/port against what's really running on the VPS (`docker ps`, `systemctl status`) before installing — `3000` is `server.js`'s documented default `PORT`, not a verified-live value, since this session has no SSH access to the VPS to check.

---

## 6. `.env.example` additions

```env
# PayPal — required for real purchase-pass / capture / webhook flows.
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
PAYPAL_WEBHOOK_ID=

# Login / registration rate limiting (see lib/rate-limit.js). Defaults shown.
# LOGIN_RATE_WINDOW_MS=900000
# LOGIN_RATE_MAX=10
# REGISTER_RATE_WINDOW_MS=3600000
# REGISTER_RATE_MAX=20

# Escape hatch — leave unset in production.
# ALLOW_IN_MEMORY_AUTH=true
```

---

## 7. Cruft removal

Deleted (all confirmed dead — referenced a prior TypeScript/Express backend at `/opt/patwago/api/src/...` and a `/opt/patwago/web/` layout that no longer exists anywhere in this repo):

- `patwago_index.html` (2,114 lines — stale pre-backend snapshot, admin panel read fake `localStorage` data)
- `patch_patwago.py` (546 lines)
- `patwago_patch.py` (513 lines)
- `scripts/patwago_audit_fix.py` (476 lines)
- `scripts/patwago_google_maps_build.py` (537 lines)
- `scripts/patwago_jwt_and_safety.py` (123 lines)
- `scripts/patwago_remove_paypal_mocks.py` (24 lines)
- `scripts/patwago_v2_audit_fix.py` (347 lines)
- `scripts/patwago_v2_polish.py` (43 lines)

Kept: `scripts/patwago_commercial_backtest.py` (live HTTPS smoke test, still relevant) and `scripts/scrape_osm_to_patwago.py` (data-import utility — has a stale infra assumption but isn't confirmed dead the way the others are).

**Total: 4,818 lines of dead code removed.**

---

## 8. Test-runner coverage — new file `scripts/check-syntax.js`

**The bug:** `npm run check` was a hardcoded chain of `node --check` calls covering only 9 of 16 shipped `.js` files — `lib/auth.js`, `lib/customer-data.js`, `lib/paypal.js`, and most of `public/app/*.js` were silently unchecked.

```js
'use strict';
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');

function jsFilesIn(dir) {
  const full = path.join(ROOT, dir);
  if (!fs.existsSync(full)) return [];
  return fs.readdirSync(full).filter((f) => f.endsWith('.js')).map((f) => path.join(dir, f));
}

const files = ['server.js', ...jsFilesIn('lib'), ...jsFilesIn('public/app')];

let failed = false;
for (const file of files) {
  try {
    execFileSync(process.execPath, ['--check', file], { cwd: ROOT, stdio: 'pipe' });
    console.log(`ok   ${file}`);
  } catch (error) {
    failed = true;
    console.error(`FAIL ${file}`);
    console.error(String(error.stderr || error.message).trim());
  }
}
if (failed) { console.error(`\n${files.length} files checked, at least one failed.`); process.exit(1); }
console.log(`\n${files.length} files checked, all OK.`);
```

`package.json`: `"check": "node scripts/check-syntax.js"` — globs `lib/` and `public/app/` instead of a hand-maintained list, so new files are automatically covered.

---

## 9. New/changed tests

- `tests/payments.test.js` (new, 95 lines) — `recordOrderCreated`, idempotency, `recordCapture` upsert + `wasAlreadyCompleted` flag, `listByCustomer`, `extractIdsFromCaptureEvent` including malformed-input handling.
- `tests/rate-limit.test.js` (new, 38 lines) — allow-under-max, block-over-max, independent keys, window reset.
- `tests/api.test.js` (+43 lines) — HTTP-level 429 test hitting the real login route 4 times with `LOGIN_RATE_MAX=3`, asserts `Retry-After` header present; HTTP-level test that registering with a 6-char password returns the server-side rejection, not just a client-side block.
- `tests/auth.test.js` (+102/-various) — password-length boundary test (7 chars rejected, exactly 8 accepted), `updateCustomer` short-password rejection, week-pass duration test. Also bumped every short test-fixture password (`'pw'`, `'x'`, etc.) to 8+ characters so the new server-side minimum doesn't break unrelated tests.
- `tests/paypal.test.js` (+30/-various) — updated all `trip`-plan price assertions from `29.99` to `49.99` to match the corrected pricing; added a `week` plan `createOrder` test.
- `tests/api.test.js` — added `lib/payments` to the fresh-module cache-clearing list in `loadFreshServer()` (its in-memory store would otherwise leak state across tests in the same file, since it wasn't being reset like the other `lib/*` modules).

**Result: 125/125 tests passing** (109 pre-existing + 16 new), **16/16 files pass `npm run check`**.

---

## 10. README.md rewrite

Previous README only documented the AI voice/translation pipeline and the analytics dashboard. Rewritten to cover: what the app actually is (single Node process, real `/app/*` pages), the full feature map (auth, marketplace, trips, Guardian Mode, payments) with file locations, the pricing table, data storage model (Postgres in production, in-memory fallback in dev/test only), rate limiting, testing commands, and deploy notes referencing the corrected Traefik config. Full text is in the commit — see `README.md`.

---

## How to apply this

The full commit is `fd98cb4` on branch `claude/commercial-grade-hardening`, based on `origin/main` at `3c672a2` — no other commits have landed on `main` since, so this should apply cleanly with either:

```bash
# Option A — if you can reach the branch directly (it only exists in the sandbox clone right now)
git remote add sandbox <path-or-url-to-sandbox-clone>
git fetch sandbox claude/commercial-grade-hardening
git checkout -b claude/commercial-grade-hardening sandbox/claude/commercial-grade-hardening
git push origin claude/commercial-grade-hardening

# Option B — rebuild from this document
# Recreate each file/change above against a fresh clone of RAYKUNJAL/patwago,
# then: npm install && npm test && npm run check   (expect 125 pass / 16 ok)
```
