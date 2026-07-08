#!/usr/bin/env node
/**
 * One-time setup: creates the MoldForge product + 4 subscription plans in your
 * PayPal business account and prints the env vars to paste into your service.
 *
 * Usage:
 *   PAYPAL_ENV=live PAYPAL_CLIENT_ID=xxx PAYPAL_CLIENT_SECRET=yyy node setup-paypal.js
 *
 * Get credentials: https://developer.paypal.com/dashboard → Apps & Credentials
 * → Create App (type: Merchant) → copy Client ID + Secret. Use the "Live" tab
 * for real payments, "Sandbox" for testing.
 */
const ENV = process.env.PAYPAL_ENV === 'live' ? 'live' : 'sandbox';
const API = ENV === 'live' ? 'https://api-m.paypal.com' : 'https://api-m.sandbox.paypal.com';
const ID = process.env.PAYPAL_CLIENT_ID, SECRET = process.env.PAYPAL_CLIENT_SECRET;
const CURRENCY = process.env.PAYPAL_CURRENCY || 'USD';
if (!ID || !SECRET) { console.error('Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET first.'); process.exit(1); }

const PLANS = [
  { key: 'PAYPAL_PLAN_MAKER_M', name: 'MoldForge Maker — monthly', price: '7.00',   interval: 'MONTH' },
  { key: 'PAYPAL_PLAN_MAKER_Y', name: 'MoldForge Maker — yearly',  price: '59.00',  interval: 'YEAR'  },
  { key: 'PAYPAL_PLAN_PRO_M',   name: 'MoldForge Pro — monthly',   price: '15.00',  interval: 'MONTH' },
  { key: 'PAYPAL_PLAN_PRO_Y',   name: 'MoldForge Pro — yearly',    price: '119.00', interval: 'YEAR'  },
];

(async () => {
  const tok = await fetch(`${API}/v1/oauth2/token`, {
    method: 'POST',
    headers: { Authorization: 'Basic ' + Buffer.from(`${ID}:${SECRET}`).toString('base64'),
               'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'grant_type=client_credentials',
  }).then(r => r.json());
  if (!tok.access_token) { console.error('Auth failed:', tok); process.exit(1); }
  const H = { Authorization: `Bearer ${tok.access_token}`, 'Content-Type': 'application/json' };

  const product = await fetch(`${API}/v1/catalogs/products`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ name: 'MoldForge', description: 'Browser-based 3D mold generator for makers',
                           type: 'DIGITAL', category: 'SOFTWARE' }),
  }).then(r => r.json());
  if (!product.id) { console.error('Product create failed:', product); process.exit(1); }
  console.log(`Product created: ${product.id}\n`);

  console.log('# Add these to your moldforge.service / shell env:');
  console.log(`PAYPAL_ENV=${ENV}`);
  for (const p of PLANS) {
    const plan = await fetch(`${API}/v1/billing/plans`, {
      method: 'POST', headers: H,
      body: JSON.stringify({
        product_id: product.id, name: p.name, status: 'ACTIVE',
        billing_cycles: [{
          frequency: { interval_unit: p.interval, interval_count: 1 },
          tenure_type: 'REGULAR', sequence: 1, total_cycles: 0,
          pricing_scheme: { fixed_price: { value: p.price, currency_code: CURRENCY } },
        }],
        payment_preferences: { auto_bill_outstanding: true, payment_failure_threshold: 2 },
      }),
    }).then(r => r.json());
    if (!plan.id) { console.error(`Plan failed (${p.name}):`, plan); process.exit(1); }
    console.log(`${p.key}=${plan.id}`);
  }
  console.log('\nDone. Restart the moldforge service and subscriptions go live.');
})();
