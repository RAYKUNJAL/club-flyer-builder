#!/usr/bin/env node
/**
 * Generate branded copies of the master site (moldstudio/) into sites/<brand>/.
 * One codebase, N brands: name, logo, colors, chatbot persona, support email.
 *
 * Usage: node build-brands.js
 * Edit BRANDS below to tweak a brand, then re-run — sites/ is fully regenerated.
 */
const fs = require('fs');
const path = require('path');

const MASTER = path.join(__dirname, 'moldstudio');
const OUT = path.join(__dirname, 'sites');

const BRANDS = [
  {
    slug: 'buildmymold',
    domain: 'buildmymold.com',
    name: 'BuildMyMold',
    logoHtml: 'Build<b>My</b>Mold',
    emoji: '🧱',
    botName: 'Buddy',
    port: 8787,
    accent: '#2dd4a7',   // fresh teal
    accent2: '#8be26b',  // lime
    accentRgb: '45,212,167',
    threeHex: '0x2dd4a7',
    tagline: 'Build your first mold in 2 minutes.',
  },
  {
    slug: 'makemymold',
    domain: 'makemymold.com',
    name: 'MakeMyMold',
    logoHtml: 'Make<b>My</b>Mold',
    emoji: '🪄',
    botName: 'Mimi',
    port: 8788,
    accent: '#c084fc',   // orchid purple
    accent2: '#f472b6',  // pink
    accentRgb: '192,132,252',
    threeHex: '0xc084fc',
    tagline: 'Make your first mold in 2 minutes.',
  },
];

const TEXT_EXT = new Set(['.html', '.js', '.css', '.md', '.json']);
// vendor libs are copied verbatim — no brand strings inside
const SKIP_REWRITE = /[\\/]vendor[\\/]/;

function rebrand(src, b) {
  return src
    .replaceAll('Mold<b>Forge</b>', b.logoHtml)
    .replaceAll('MoldForge Studio', `${b.name} Studio`)
    .replaceAll('MoldForge', b.name)
    .replaceAll('moldforge.app', b.domain)
    .replaceAll('moldforge', b.slug)
    .replaceAll('Forgey', b.botName)
    .replaceAll('🧊', b.emoji)
    .replaceAll('#ff7a59', b.accent)
    .replaceAll('#ffb35c', b.accent2)
    .replaceAll('255,122,89', b.accentRgb)
    .replaceAll('0xff7a59', b.threeHex)
    .replaceAll('Turn any shape into a <em>3D-printable mold</em> in 2 minutes.',
                `Turn any shape into a <em>3D-printable mold</em>. ${b.tagline.replace(/^[A-Z]/, c => c)}`)
    .replaceAll("PORT || 8787", `PORT || ${b.port}`);
}

function copyDir(from, to, b) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    if (entry.name === 'purchases.jsonl') continue; // never copy a ledger between sites
    const s = path.join(from, entry.name), d = path.join(to, entry.name);
    if (entry.isDirectory()) { copyDir(s, d, b); continue; }
    if (TEXT_EXT.has(path.extname(entry.name)) && !SKIP_REWRITE.test(s)) {
      fs.writeFileSync(d, rebrand(fs.readFileSync(s, 'utf8'), b));
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

fs.rmSync(OUT, { recursive: true, force: true });
for (const b of BRANDS) {
  copyDir(MASTER, path.join(OUT, b.slug), b);
  console.log(`✓ sites/${b.slug}  (${b.domain}, port ${b.port}, accent ${b.accent} ${b.emoji})`);
}
console.log('\nDone. Each site runs with: node sites/<brand>/support-bot/server.js');
