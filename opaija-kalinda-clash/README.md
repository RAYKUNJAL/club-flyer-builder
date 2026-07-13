# 🥁 OPAIJA: Kalinda Clash — HTML5 Prototype

A playable rhythm-fighting-game prototype set in the OPAIJA animated series universe.
Pure HTML5 Canvas + Web Audio — no dependencies, no build step.

**Rhythm. Roots. Resistance.**

## Play

Open `index.html` in any modern browser (or serve the folder with any static server).
Sound starts on your first key press (browser autoplay rules).

## The Fighters

| | Jabari “Jabs” Henry | Marius Vale |
|---|---|---|
| Role | Drummer / Beat Strategist | False One Drum / Silence Strategist |
| Style | Fast, close-range pressure | Slow, long staff range, heavy hits |
| Special | **Riddim Wave** — projectile shockwave | **Silence Pulse** — close AoE that drains Lavway meter and *silences* you (no rhythm bonus for 3.5s) |
| Super | **Whole Vibration** — 8-hit drum rush | **Memory Theft** — massive strike that steals your remaining meter |

## Core Mechanics

- **Riddim timing** — the stage percussion runs at 158 BPM (a soca engine-room pattern
  generated with Web Audio). Press an attack **on the pulse** (watch the RIDDIM indicator,
  bottom-center) for **+30% damage and double meter gain**.
- **Lavway Drive** — the super meter. Builds from dealing/taking damage, doubles on-beat.
  At 100% unleash your super.
- **Silence** — Marius' pulse muffles the music and cuts you off from the beat bonus.
- Blocking (hold away), jumping, launchers, combos, chip damage, best-of-3 rounds, 99s timer.

## Controls

| Action | P1 | P2 |
|---|---|---|
| Move | A / D | ← / → |
| Jump | W | ↑ |
| Block | hold away from opponent | hold away |
| Light | F | K |
| Heavy | G | L |
| Special | H | O |
| Super (needs full meter) | SPACE | I |
| Pause | ESC / P | — |

Modes: **VS CPU** (beat-aware AI) and **VS Player** (local 2P on one keyboard).

## Assets

All fighter visuals are the **official character-sheet art**. `assets/` contains:

- `logo.jpg` — the OPAIJA logo (title screen)
- `*-face.png` — front head portraits (battle HUD)
- `*-pose.png` — full action-pose panels with quotes (character select cards)
- `*-side / *-front / *-relax / *-action.png` — figures cut out of each sheet's
  turnaround, relaxed and action panels with transparent backgrounds. These are the
  in-battle sprites, animated paper-doll style on canvas: side view for idle/walk/jump,
  action pose (with lunge, tilt and swing-arc FX) for attacks and supers, front view
  for hit/block reactions, relaxed pose for round victory.
