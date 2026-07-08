# MoldForge — VPS deployment (site + AI support bot on your local Qwen)

Everything runs on one VPS: the static site, the support-bot proxy, and your
locally-hosted Qwen model. No data leaves your server.

```
Browser ──HTTPS──> nginx ──> server.js (port 8787)
                                ├── serves the MoldForge site
                                └── /api/chat ──> local Qwen (Ollama/vLLM, port 11434)
```

## 1. Install a local LLM runtime (pick one)

**Option A — Ollama (easiest, recommended):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b-instruct        # needs ~5 GB RAM; use qwen2.5:14b-instruct if you have 16 GB+
```
Ollama automatically exposes an OpenAI-compatible API at `http://127.0.0.1:11434/v1`.

**Option B — vLLM (GPU servers, higher throughput):**
```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct --port 11434
```

## 2. Run the bot server

Requires Node 18+ (`apt install nodejs`). No npm install needed — zero dependencies.

```bash
cd moldstudio/support-bot
LLM_BASE_URL=http://127.0.0.1:11434/v1 \
LLM_MODEL=qwen2.5:7b-instruct \
PORT=8787 \
node server.js
```

Open `http://your-vps:8787` — the site loads and the 💬 bubble answers questions.

## 3. Keep it running (systemd)

`/etc/systemd/system/moldforge.service`:
```ini
[Unit]
Description=MoldForge site + support bot
After=network.target ollama.service

[Service]
WorkingDirectory=/opt/moldforge/moldstudio/support-bot
Environment=LLM_BASE_URL=http://127.0.0.1:11434/v1
Environment=LLM_MODEL=qwen2.5:7b-instruct
Environment=PORT=8787
ExecStart=/usr/bin/node server.js
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now moldforge
```

## 4. nginx in front (SSL)

```nginx
server {
  server_name moldforge.app;
  location / {
    proxy_pass http://127.0.0.1:8787;
    proxy_http_version 1.1;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;            # required for streaming chat
    proxy_read_timeout 300s;
  }
}
```
Then `certbot --nginx -d moldforge.app`.

## Customizing the bot

- **Product knowledge / "training"**: edit `knowledge.md` — it is injected as the system prompt
  on every request. Restart the service after editing. Add new FAQs, policies, tone rules there.
- **Model**: set `LLM_MODEL` (e.g. `qwen2.5:14b-instruct`, `qwen3:8b`) — anything your runtime serves.
- **Limits**: 20 messages/min per IP, 16-turn history, 700 token replies (`MAX_TOKENS`).
- **Fallback**: if the LLM is down, users are told to email support@moldforge.app.

## PayPal payments

The pricing page sells: Day Pass $5 and Lifetime $249 (one-time), Maker $7/mo·$59/yr and
Pro $15/mo·$119/yr (subscriptions). Buttons open a PayPal checkout modal; until you configure
credentials, they gracefully fall back to plain links.

1. Get REST credentials at https://developer.paypal.com/dashboard → Apps & Credentials →
   Create App (Merchant). Use the **Live** tab for real money, **Sandbox** to test.
2. Create the subscription plans (one time):
   ```bash
   PAYPAL_ENV=live PAYPAL_CLIENT_ID=xxx PAYPAL_CLIENT_SECRET=yyy node setup-paypal.js
   ```
   It prints four `PAYPAL_PLAN_*` ids.
3. Add all of it to the service environment and restart:
   ```ini
   Environment=PAYPAL_ENV=live
   Environment=PAYPAL_CLIENT_ID=xxx
   Environment=PAYPAL_CLIENT_SECRET=yyy
   Environment=PAYPAL_PLAN_MAKER_M=P-...
   Environment=PAYPAL_PLAN_MAKER_Y=P-...
   Environment=PAYPAL_PLAN_PRO_M=P-...
   Environment=PAYPAL_PLAN_PRO_Y=P-...
   ```

Details:
- Prices live server-side in `paypal.js` (`ONE_TIME`) and in the PayPal plans — the browser
  can't tamper with them.
- Every completed payment is appended to `support-bot/purchases.jsonl` with a generated
  license key (shown to the buyer after checkout). Back this file up.
- One-time payments are verified by server-side capture; subscriptions are verified against
  the PayPal API before being recorded.
- Refunds: do them from the PayPal dashboard (14-day policy).

## Test without a model

```bash
node mock-llm.js &        # fake OpenAI endpoint on :11434
node server.js            # bot works end-to-end with canned streaming replies
```
