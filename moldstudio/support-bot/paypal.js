/**
 * PayPal checkout for MoldForge — one-time purchases (Day Pass, Lifetime) via
 * the Orders API, subscriptions (Maker/Pro) via the Subscriptions API.
 * Zero dependencies; prices live server-side so the client can't tamper.
 *
 * Env vars:
 *   PAYPAL_ENV            sandbox | live            (default sandbox)
 *   PAYPAL_CLIENT_ID      REST app client id        (required to enable payments)
 *   PAYPAL_CLIENT_SECRET  REST app secret           (required to enable payments)
 *   PAYPAL_PLAN_MAKER_M / PAYPAL_PLAN_MAKER_Y       subscription plan ids
 *   PAYPAL_PLAN_PRO_M   / PAYPAL_PLAN_PRO_Y         (create with setup-paypal.js)
 *   PAYPAL_CURRENCY       default USD
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ENV = process.env.PAYPAL_ENV === 'live' ? 'live' : 'sandbox';
const API = ENV === 'live' ? 'https://api-m.paypal.com' : 'https://api-m.sandbox.paypal.com';
const CLIENT_ID = process.env.PAYPAL_CLIENT_ID || '';
const CLIENT_SECRET = process.env.PAYPAL_CLIENT_SECRET || '';
const CURRENCY = process.env.PAYPAL_CURRENCY || 'USD';
const ENABLED = Boolean(CLIENT_ID && CLIENT_SECRET);
const LEDGER = path.join(__dirname, 'purchases.jsonl');

// Server-side price list — single source of truth.
const ONE_TIME = {
  daypass:  { name: 'MoldForge Day Pass — 24h of everything + commercial license', price: '5.00' },
  lifetime: { name: 'MoldForge Lifetime — everything forever + lifetime commercial license', price: '249.00' },
};
const PLANS = {
  'maker-m': process.env.PAYPAL_PLAN_MAKER_M || '',
  'maker-y': process.env.PAYPAL_PLAN_MAKER_Y || '',
  'pro-m':   process.env.PAYPAL_PLAN_PRO_M || '',
  'pro-y':   process.env.PAYPAL_PLAN_PRO_Y || '',
};

/* ---------------- helpers ---------------- */
let tokenCache = { token: null, exp: 0 };
async function accessToken() {
  if (tokenCache.token && Date.now() < tokenCache.exp - 60_000) return tokenCache.token;
  const r = await fetch(`${API}/v1/oauth2/token`, {
    method: 'POST',
    headers: {
      Authorization: 'Basic ' + Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString('base64'),
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: 'grant_type=client_credentials',
  });
  if (!r.ok) throw new Error(`paypal auth ${r.status}`);
  const j = await r.json();
  tokenCache = { token: j.access_token, exp: Date.now() + j.expires_in * 1000 };
  return tokenCache.token;
}
async function pp(method, url, body) {
  const r = await fetch(`${API}${url}`, {
    method,
    headers: { Authorization: `Bearer ${await accessToken()}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  const json = text ? JSON.parse(text) : {};
  if (!r.ok) { const e = new Error(`paypal ${r.status}: ${text.slice(0, 300)}`); e.status = r.status; throw e; }
  return json;
}
function json(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}
async function readBody(req) {
  let b = '';
  for await (const c of req) { b += c; if (b.length > 50_000) throw new Error('too big'); }
  return JSON.parse(b || '{}');
}
function licenseKey(sku) {
  return `MF-${sku.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 4)}-${crypto.randomBytes(8).toString('hex').toUpperCase()}`;
}
function record(entry) {
  fs.appendFileSync(LEDGER, JSON.stringify({ ...entry, at: new Date().toISOString(), env: ENV }) + '\n');
}

/* ---------------- routes ---------------- */
async function handle(req, res) {
  try {
    if (req.method === 'GET' && req.url === '/api/paypal/config') {
      return json(res, 200, ENABLED
        ? { enabled: true, env: ENV, clientId: CLIENT_ID, currency: CURRENCY, plans: PLANS,
            oneTime: Object.fromEntries(Object.entries(ONE_TIME).map(([k, v]) => [k, v.price])) }
        : { enabled: false });
    }
    if (!ENABLED) return json(res, 503, { error: 'Payments are not configured yet.' });

    if (req.method === 'POST' && req.url === '/api/paypal/create-order') {
      const { sku } = await readBody(req);
      const item = ONE_TIME[sku];
      if (!item) return json(res, 400, { error: 'Unknown product' });
      const order = await pp('POST', '/v2/checkout/orders', {
        intent: 'CAPTURE',
        purchase_units: [{
          description: item.name.slice(0, 127),
          custom_id: sku,
          amount: { currency_code: CURRENCY, value: item.price },
        }],
      });
      return json(res, 200, { orderId: order.id });
    }

    if (req.method === 'POST' && req.url === '/api/paypal/capture-order') {
      const { orderId } = await readBody(req);
      if (!/^[A-Z0-9-]{5,40}$/i.test(orderId || '')) return json(res, 400, { error: 'Bad order id' });
      const cap = await pp('POST', `/v2/checkout/orders/${orderId}/capture`, {});
      const unit = cap.purchase_units?.[0];
      const capture = unit?.payments?.captures?.[0];
      if (cap.status !== 'COMPLETED' || !capture) return json(res, 402, { error: 'Payment not completed' });
      const sku = capture.custom_id || unit?.custom_id || 'unknown';
      const key = licenseKey(sku);
      record({
        type: 'order', sku, license: key, orderId, captureId: capture.id,
        amount: capture.amount, payer: cap.payer?.email_address || null,
      });
      return json(res, 200, { ok: true, license: key, sku });
    }

    if (req.method === 'POST' && req.url === '/api/paypal/record-subscription') {
      const { subscriptionId, sku } = await readBody(req);
      if (!/^I-[A-Z0-9]{5,30}$/i.test(subscriptionId || '')) return json(res, 400, { error: 'Bad subscription id' });
      const sub = await pp('GET', `/v1/billing/subscriptions/${subscriptionId}`);
      if (!['ACTIVE', 'APPROVED'].includes(sub.status)) return json(res, 402, { error: `Subscription is ${sub.status}` });
      if (!Object.values(PLANS).includes(sub.plan_id)) return json(res, 400, { error: 'Unknown plan' });
      const key = licenseKey(sku || 'sub');
      record({
        type: 'subscription', sku: sku || null, license: key, subscriptionId: sub.id,
        planId: sub.plan_id, payer: sub.subscriber?.email_address || null, status: sub.status,
      });
      return json(res, 200, { ok: true, license: key });
    }

    json(res, 404, { error: 'Not found' });
  } catch (err) {
    console.error('[paypal]', err.message);
    json(res, 500, { error: 'Payment hiccup — nothing was charged twice. Try again or email support@moldforge.app.' });
  }
}

module.exports = { handle, ENABLED };
