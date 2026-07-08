/* MoldForge checkout — PayPal Smart Buttons on the pricing cards.
   If payments aren't configured on the server, buttons keep their normal links. */
(function () {
  'use strict';

  const PRODUCTS = {
    daypass:  { title: '⚡ Day Pass',  desc: '24 hours of everything + commercial license for what you make today', once: '$5' },
    lifetime: { title: '🏆 Lifetime',  desc: 'Everything in Pro, forever. One payment.', once: '$249' },
    maker:    { title: '🛠 Maker',     desc: 'Unlimited downloads, 50 projects, 3MF export', m: '$7/mo', y: '$59/yr' },
    pro:      { title: '🚀 Pro',       desc: 'Commercial license you keep forever + everything unlimited', m: '$15/mo', y: '$119/yr' },
  };

  let config = null;

  const css = `
  #mf-pay{position:fixed;inset:0;background:rgba(10,12,24,.85);backdrop-filter:blur(8px);z-index:9990;
    display:none;align-items:center;justify-content:center;padding:16px;font-family:'Nunito',system-ui,sans-serif}
  #mf-pay.open{display:flex}
  .mf-pay-box{background:#171b2e;border:1px solid #2a3050;border-radius:20px;width:min(440px,100%);
    padding:28px;color:#eef0fb;max-height:92vh;overflow-y:auto}
  .mf-pay-box h3{font-size:20px;font-weight:900;margin:0 0 4px}
  .mf-pay-box .d{color:#9aa3c7;font-weight:600;font-size:13.5px;margin-bottom:18px}
  .mf-cycle{display:flex;gap:8px;margin-bottom:16px}
  .mf-cycle button{flex:1;background:#1d2238;border:2px solid #2a3050;border-radius:12px;color:#eef0fb;
    font-family:inherit;font-weight:800;font-size:14px;padding:12px;cursor:pointer}
  .mf-cycle button.on{border-color:#ff7a59;background:rgba(255,122,89,.08)}
  .mf-cycle small{display:block;color:#3ddc97;font-size:11px;font-weight:800}
  #mf-pay-buttons{min-height:150px}
  .mf-pay-close{margin-top:14px;width:100%;background:none;border:1px solid #2a3050;border-radius:10px;
    color:#9aa3c7;font-family:inherit;font-weight:800;padding:10px;cursor:pointer}
  .mf-pay-ok{text-align:center;padding:12px 0}
  .mf-pay-ok .big{font-size:44px}
  .mf-pay-ok h4{font-size:19px;font-weight:900;margin:8px 0}
  .mf-pay-ok .lic{background:#1d2238;border:1px dashed #3ddc97;border-radius:10px;padding:12px;
    font-weight:900;font-size:15px;color:#3ddc97;letter-spacing:.5px;user-select:all}
  .mf-pay-ok p{color:#9aa3c7;font-weight:600;font-size:12.5px}`;

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const modal = document.createElement('div');
  modal.id = 'mf-pay';
  modal.innerHTML = `<div class="mf-pay-box">
    <h3 id="mf-pay-title"></h3>
    <div class="d" id="mf-pay-desc"></div>
    <div class="mf-cycle" id="mf-pay-cycle" style="display:none">
      <button data-cycle="m"></button>
      <button data-cycle="y"></button>
    </div>
    <div id="mf-pay-buttons"></div>
    <button class="mf-pay-close">Never mind</button>
  </div>`;
  document.body.appendChild(modal);
  modal.querySelector('.mf-pay-close').onclick = close;
  modal.addEventListener('click', e => { if (e.target === modal) close(); });

  function close() { modal.classList.remove('open'); }

  let sdkParams = null;
  function loadSdk(params) {
    return new Promise((ok, fail) => {
      if (sdkParams === params && window.paypal) return ok();
      document.querySelectorAll('script[data-mf-paypal]').forEach(s => s.remove());
      delete window.paypal;
      const s = document.createElement('script');
      s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(config.clientId)}&currency=${config.currency}&${params}`;
      s.dataset.mfPaypal = '1';
      s.onload = () => { sdkParams = params; ok(); };
      s.onerror = fail;
      document.head.appendChild(s);
    });
  }

  function success(license, msg) {
    modal.querySelector('.mf-pay-box').innerHTML = `<div class="mf-pay-ok">
      <div class="big">🎉</div>
      <h4>You're in! Thank you!</h4>
      ${license ? `<div class="lic">${license}</div>
      <p style="margin-top:8px">This is your license key — screenshot it or write it down.<br>It's also in your PayPal receipt.</p>` : ''}
      <p>${msg || ''}</p>
      <button class="mf-pay-close" onclick="document.getElementById('mf-pay').classList.remove('open')">Back to making molds →</button>
    </div>`;
  }

  async function renderButtons(plan, cycle) {
    const holder = modal.querySelector('#mf-pay-buttons');
    holder.innerHTML = '<div style="text-align:center;color:#9aa3c7;font-weight:700;padding:20px">Loading secure checkout…</div>';
    try {
      if (plan === 'daypass' || plan === 'lifetime') {
        await loadSdk('intent=capture');
        holder.innerHTML = '';
        window.paypal.Buttons({
          style: { color: 'gold', shape: 'pill', label: 'pay', height: 45 },
          createOrder: () => fetch('/api/paypal/create-order', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sku: plan }),
          }).then(r => r.json()).then(d => { if (!d.orderId) throw new Error(d.error); return d.orderId; }),
          onApprove: data => fetch('/api/paypal/capture-order', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ orderId: data.orderID }),
          }).then(r => r.json()).then(d => {
            if (!d.ok) throw new Error(d.error);
            success(d.license, plan === 'daypass' ? 'Your 24 hours start now — go make something!' : 'Lifetime access unlocked. Welcome to the founders club!');
          }),
          onError: () => alert('Payment did not complete. You were not charged — please try again.'),
        }).render(holder);
      } else {
        const planId = config.plans[`${plan}-${cycle}`];
        if (!planId) { holder.innerHTML = '<div style="color:#ff6b81;font-weight:700;text-align:center;padding:16px">This plan isn\'t live yet — email support@moldforge.app</div>'; return; }
        await loadSdk('intent=subscription&vault=true');
        holder.innerHTML = '';
        window.paypal.Buttons({
          style: { color: 'gold', shape: 'pill', label: 'subscribe', height: 45 },
          createSubscription: (d, actions) => actions.subscription.create({ plan_id: planId }),
          onApprove: data => fetch('/api/paypal/record-subscription', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscriptionId: data.subscriptionID, sku: `${plan}-${cycle}` }),
          }).then(r => r.json()).then(d => success(d.license, 'Subscription active — cancel anytime from your PayPal account.')),
          onError: () => alert('Payment did not complete. You were not charged — please try again.'),
        }).render(holder);
      }
    } catch (e) {
      holder.innerHTML = '<div style="color:#ff6b81;font-weight:700;text-align:center;padding:16px">Checkout could not load. Please try again or email support@moldforge.app</div>';
    }
  }

  function open(plan) {
    const p = PRODUCTS[plan];
    if (!p) return;
    // reset box content if a previous success replaced it
    if (!modal.querySelector('#mf-pay-title')) { modal.remove(); location.reload(); return; }
    modal.querySelector('#mf-pay-title').textContent = p.title;
    modal.querySelector('#mf-pay-desc').textContent = p.desc;
    const cyc = modal.querySelector('#mf-pay-cycle');
    if (p.m) {
      cyc.style.display = 'flex';
      const [bm, by] = cyc.querySelectorAll('button');
      bm.innerHTML = `${p.m}<small>&nbsp;</small>`;
      by.innerHTML = `${p.y}<small>save with yearly ✓</small>`;
      let cycle = 'y';
      const paint = () => { bm.classList.toggle('on', cycle === 'm'); by.classList.toggle('on', cycle === 'y'); renderButtons(plan, cycle); };
      bm.onclick = () => { cycle = 'm'; paint(); };
      by.onclick = () => { cycle = 'y'; paint(); };
      paint();
    } else {
      cyc.style.display = 'none';
      renderButtons(plan);
    }
    modal.classList.add('open');
  }

  // wire pricing buttons
  fetch('/api/paypal/config').then(r => r.json()).then(c => {
    config = c;
    if (!c.enabled) return; // keep normal links until payments are configured
    document.querySelectorAll('[data-plan]').forEach(el => {
      el.addEventListener('click', e => { e.preventDefault(); open(el.dataset.plan); });
    });
  }).catch(() => {});

  window.MFCheckout = { open: p => config?.enabled && open(p) };
})();
