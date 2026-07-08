# This repo

- **🧊 MoldForge** (`moldstudio/`) — browser-based 3D mold generator (Meshcast competitor).
  Landing page + 3D studio + AI support bot + PayPal checkout. See `moldstudio/support-bot/README.md`
  for VPS deployment and `docs/MESHCAST_COMPETITOR_ANALYSIS.md` for the strategy behind it.
  Quick start: `node moldstudio/support-bot/server.js` → http://localhost:8787
- **🎉 Club Flyer Builder** (below) — flyer template builder for Wefetepass.

---

# 🎉 Club Flyer Builder

A browser-based club/event flyer template builder built with HTML5 Canvas. No dependencies — runs entirely in the browser.

## Features

- 🎨 **4 Club Templates** — Neon Nights, Gold Rush, Minimal, Caribbean
- 🖱️ **Drag & Drop** elements on the canvas
- ✏️ **Editable Text** — double-click any text element to edit inline
- 🖼️ **Image Upload** — drop your DJ or artist photo onto the flyer
- 🔷 **Shape Tools** — rectangles, circles, stars, lines, diamonds
- 🎨 **Design Controls** — gradient backgrounds, accent colors, typography
- 💡 **Decorations** — glow effects, star particles, border frames, scanlines
- 📐 **Multiple Sizes** — 6×8 Print, Instagram, Facebook, Square
- 💾 **Export PNG** — full resolution download
- 💾 **Save Project** — JSON project file to resume later

## Usage

1. Open `club-flyer-builder.html` in any modern browser
2. Choose a template from the left sidebar
3. Edit event details in the right panel → click **Apply to Flyer**
4. Drag elements around the canvas to position them
5. Use the Design tab to customize colors, fonts, and effects
6. Click **Export PNG** to download your flyer

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Delete` / `Backspace` | Delete selected element |
| `Ctrl+D` | Duplicate selected element |
| `Escape` | Deselect all |
| `Double-click` | Edit text element |

## Tech Stack

- Vanilla HTML5 / CSS / JavaScript
- HTML5 Canvas API (no external canvas lib)
- Google Fonts (Bebas Neue, Orbitron, Inter)

---
Built for Wefetepass — event ticketing platform for Trinidad & Tobago.
