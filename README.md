# 🧵 StringForge 3D — String Art Generator for 3D Printers

A free, browser-based tool that turns any photo into 3D-printable string art — inspired by stringart3d.com, rebuilt with no paywall, no accounts, and more export options. Everything runs client-side: your photos never leave the browser.

**→ Open `index.html` in any modern browser (or host it on GitHub Pages).**

## What it does

1. **Upload a photo** (or use the built-in demo image), then crop, zoom, and tune brightness/contrast/invert.
2. **Generate** — a greedy string-art solver (running in a Web Worker) places thousands of chords between pins on the frame, live-drawing the preview as it solves. The whole portrait is one continuous line.
3. **Export** printer-ready files:

| Export | What it's for |
|--------|---------------|
| **`.gcode`** | Direct-print file: prints a solid frame, then draws every string as a taut mid-air extrusion bridge and locks the ends under the frame walls. Something slicers can't produce from a mesh. |
| **`.stl`** | Frame + strings mesh, sliceable in Bambu Studio / PrusaSlicer / Cura with your own profile (enable thin-wall detection). |
| **`.svg`** | Vector line art for laser engraving or paper printing. |
| **`.txt`** | Numbered pin sequence for classic nail-and-thread string art, with thread-length estimate. |
| **`.png`** | High-res preview render. |

## Features

- 🟣 **Three frame shapes** — circle, square, heart
- 🎚️ **Detail presets** (Draft / Standard / Fine) plus full manual control over pins, strings, string darkness, and min pin separation
- 🖨️ **Printer presets** — Generic Marlin/Klipper, Ender-3, Prusa MK3S/MK4, Bambu Lab A1 mini / A1 / P1 / X1, Voron 300 — with bed-size-aware frame limits
- ⚙️ **Advanced print settings** — layer height, temps, frame width, string speed/flow, skirt
- 📊 **Live estimates** — string count, thread length, print time, filament grams
- 🔒 **Fully private** — one static HTML file, zero dependencies, no server, works offline

## How the G-code works

- Base: 5 solid frame layers (concentric perimeter loops) with an optional skirt.
- Strings: chords are split across layers (~280 per layer). Each layer prints the chords first as fast bridges with full part cooling — their endpoints land on the frame band below — then prints the frame walls **over** the string ends to lock them in.
- Top: 3 capping frame layers.
- Conservative Marlin-flavour commands (G28, absolute XYZ, relative E, PLA temps). Always preview G-code before printing and watch the first layers.

Recommended: PLA, 0.4 mm nozzle, dark filament (or the invert option + white filament).

---

## 🎉 Club Flyer Builder (also in this repo)

`club-flyer-builder.html` — a browser-based club/event flyer template builder with drag-and-drop canvas editing, 4 templates, image upload, shape tools, and PNG export. Built for Wefetepass — event ticketing platform for Trinidad & Tobago. Open the file in a browser to use it.
