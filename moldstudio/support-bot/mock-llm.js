#!/usr/bin/env node
/**
 * Mock OpenAI-compatible LLM endpoint for testing the support bot without a GPU.
 * Streams a canned reply in OpenAI SSE format on :11434 (same port Ollama uses).
 */
const http = require('http');

const REPLY = "Hi! I'm a mock Qwen 🙂 On your VPS, this exact reply will come from your real local model instead. Everything upstream of me — the widget, streaming, knowledge base — is working.";

http.createServer(async (req, res) => {
  if (req.method !== 'POST' || !req.url.includes('/chat/completions')) {
    res.writeHead(404); return res.end();
  }
  for await (const _ of req) { /* drain */ }
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
  const words = REPLY.split(' ');
  let i = 0;
  const timer = setInterval(() => {
    if (i >= words.length) {
      res.write('data: [DONE]\n\n');
      clearInterval(timer);
      return res.end();
    }
    const chunk = { choices: [{ delta: { content: (i ? ' ' : '') + words[i++] } }] };
    res.write(`data: ${JSON.stringify(chunk)}\n\n`);
  }, 30);
}).listen(Number(process.env.PORT_MOCK || 11434), () => console.log('mock LLM on :11434'));
