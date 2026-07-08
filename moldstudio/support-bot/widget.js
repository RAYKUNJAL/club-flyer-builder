/* MoldForge support chat widget — streams from /api/chat (local Qwen LLM). */
(function () {
  'use strict';

  const css = `
  #mf-chat-bubble{position:fixed;bottom:22px;right:22px;width:58px;height:58px;border-radius:50%;
    background:linear-gradient(135deg,#ff7a59,#ffb35c);color:#26140c;font-size:26px;display:flex;
    align-items:center;justify-content:center;cursor:pointer;box-shadow:0 10px 30px rgba(255,122,89,.45);
    z-index:9998;transition:.15s;border:none}
  #mf-chat-bubble:hover{transform:scale(1.08)}
  @media(max-width:900px){#mf-chat-bubble{bottom:70px}}
  #mf-chat{position:fixed;bottom:92px;right:22px;width:min(380px,calc(100vw - 24px));height:min(560px,calc(100vh - 120px));
    background:#171b2e;border:1px solid #2a3050;border-radius:18px;z-index:9999;display:none;flex-direction:column;
    overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.55);font-family:'Nunito',system-ui,sans-serif;color:#eef0fb}
  #mf-chat.open{display:flex}
  @media(max-width:900px){#mf-chat{bottom:70px;right:12px}}
  .mf-head{display:flex;align-items:center;gap:10px;padding:14px 16px;background:#1d2238;border-bottom:1px solid #2a3050}
  .mf-head .ava{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#ff7a59,#ffb35c);
    display:flex;align-items:center;justify-content:center;font-size:19px}
  .mf-head .t{font-weight:800;font-size:14.5px}
  .mf-head .s{font-size:11px;color:#3ddc97;font-weight:700}
  .mf-head button{margin-left:auto;background:none;border:none;color:#9aa3c7;font-size:20px;cursor:pointer}
  .mf-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
  .mf-msg{max-width:85%;padding:10px 14px;border-radius:14px;font-size:13.5px;font-weight:600;line-height:1.5;
    white-space:pre-wrap;word-wrap:break-word}
  .mf-msg.bot{background:#1d2238;border:1px solid #2a3050;border-bottom-left-radius:4px;align-self:flex-start}
  .mf-msg.user{background:linear-gradient(135deg,#ff7a59,#ffb35c);color:#26140c;font-weight:700;
    border-bottom-right-radius:4px;align-self:flex-end}
  .mf-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 8px}
  .mf-chips button{background:#1d2238;border:1px solid #2a3050;color:#9aa3c7;font-size:11.5px;font-weight:800;
    padding:6px 12px;border-radius:999px;cursor:pointer;font-family:inherit}
  .mf-chips button:hover{border-color:#6ea8ff;color:#eef0fb}
  .mf-input{display:flex;gap:8px;padding:12px;border-top:1px solid #2a3050;background:#1d2238}
  .mf-input input{flex:1;background:#171b2e;border:1px solid #2a3050;border-radius:10px;color:#eef0fb;
    font-family:inherit;font-weight:600;font-size:13.5px;padding:11px 13px;outline:none}
  .mf-input input:focus{border-color:#6ea8ff}
  .mf-input button{background:linear-gradient(135deg,#ff7a59,#ffb35c);border:none;border-radius:10px;width:44px;
    font-size:17px;cursor:pointer}
  .mf-input button:disabled{opacity:.5;cursor:not-allowed}
  .mf-typing i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#9aa3c7;margin-right:3px;
    animation:mfB 1s infinite}
  .mf-typing i:nth-child(2){animation-delay:.15s}.mf-typing i:nth-child(3){animation-delay:.3s}
  @keyframes mfB{0%,100%{opacity:.3;transform:translateY(0)}50%{opacity:1;transform:translateY(-3px)}}
  .mf-note{font-size:10.5px;color:#9aa3c7;text-align:center;padding:0 12px 8px;font-weight:600;background:#1d2238}`;

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const bubble = document.createElement('button');
  bubble.id = 'mf-chat-bubble';
  bubble.setAttribute('aria-label', 'Chat with support');
  bubble.textContent = '💬';

  const panel = document.createElement('div');
  panel.id = 'mf-chat';
  panel.innerHTML = `
    <div class="mf-head">
      <div class="ava">🤖</div>
      <div><div class="t">Forgey — MoldForge support</div><div class="s">● online, replies instantly</div></div>
      <button aria-label="Close" id="mf-close">✕</button>
    </div>
    <div class="mf-msgs" id="mf-msgs"></div>
    <div class="mf-chips" id="mf-chips"></div>
    <div class="mf-input">
      <input id="mf-in" placeholder="Ask me anything…" maxlength="1000">
      <button id="mf-send" aria-label="Send">➤</button>
    </div>
    <div class="mf-note">AI assistant — for billing or refunds email support@moldforge.app</div>`;

  document.body.appendChild(bubble);
  document.body.appendChild(panel);

  const msgsEl = panel.querySelector('#mf-msgs');
  const chipsEl = panel.querySelector('#mf-chips');
  const inputEl = panel.querySelector('#mf-in');
  const sendEl = panel.querySelector('#mf-send');

  const CHIPS = [
    'How do I make a candle mold?',
    'Will my shape pop out?',
    'Can I sell what I make?',
    'What print settings should I use?',
  ];
  const history = JSON.parse(sessionStorage.getItem('mf-chat') || '[]');
  let busy = false;

  function addMsg(role, text) {
    const el = document.createElement('div');
    el.className = 'mf-msg ' + (role === 'user' ? 'user' : 'bot');
    el.textContent = text;
    msgsEl.appendChild(el);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return el;
  }
  function renderChips() {
    chipsEl.innerHTML = '';
    if (history.length) return;
    CHIPS.forEach(q => {
      const b = document.createElement('button');
      b.textContent = q;
      b.onclick = () => send(q);
      chipsEl.appendChild(b);
    });
  }
  function save() { sessionStorage.setItem('mf-chat', JSON.stringify(history.slice(-16))); }

  async function send(text) {
    text = (text || inputEl.value).trim();
    if (!text || busy) return;
    inputEl.value = '';
    busy = true; sendEl.disabled = true;
    history.push({ role: 'user', content: text });
    addMsg('user', text);
    renderChips();

    const botEl = addMsg('bot', '');
    botEl.innerHTML = '<span class="mf-typing"><i></i><i></i><i></i></span>';
    let answer = '';

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }),
      });
      if (!resp.ok) {
        const e = await resp.json().catch(() => ({}));
        throw new Error(e.error || 'offline');
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          const s = line.trim();
          if (!s.startsWith('data:')) continue;
          const payload = s.slice(5).trim();
          if (payload === '[DONE]') continue;
          try {
            const delta = JSON.parse(payload).choices?.[0]?.delta?.content;
            if (delta) {
              answer += delta;
              botEl.textContent = answer;
              msgsEl.scrollTop = msgsEl.scrollHeight;
            }
          } catch { /* partial json chunk */ }
        }
      }
      if (!answer) throw new Error('empty');
      history.push({ role: 'assistant', content: answer });
      save();
    } catch (err) {
      botEl.textContent = (err && err.message && err.message !== 'offline' && err.message !== 'empty')
        ? err.message
        : "I'm having trouble connecting right now 😴 — please email support@moldforge.app and a human will help within 24h.";
    } finally {
      busy = false; sendEl.disabled = false; inputEl.focus();
    }
  }

  function open() {
    panel.classList.add('open');
    bubble.textContent = '✕';
    if (!msgsEl.children.length) {
      if (history.length) history.forEach(m => addMsg(m.role, m.content));
      else addMsg('bot', "Hi, I'm Forgey! 👋 I know everything about making molds with MoldForge — printing, pouring, pricing, all of it. What can I help with?");
      renderChips();
    }
    inputEl.focus();
  }
  function close() { panel.classList.remove('open'); bubble.textContent = '💬'; }

  bubble.onclick = () => (panel.classList.contains('open') ? close() : open());
  panel.querySelector('#mf-close').onclick = close;
  sendEl.onclick = () => send();
  inputEl.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

  window.MFChat = { open, close };
})();
