# PatWaGo App UI — Screen Prototypes

Static HTML/CSS prototypes of the PatWaGo mobile app screens, matching the visual style provided (dark hero, green/gold Jamaica branding, card-based listings).

## Screens

| File | Screen |
|------|--------|
| `index.html` | Splash / welcome screen |
| `home.html` | Home — quick actions, discover banner, popular destinations, bottom nav |
| `tours.html` | Tours & Attractions listing — filter chips, tour cards |
| `tour-detail.html` | Tour detail — photo gallery, info, booking bar |

Open `index.html` in a browser to start; screens link to each other (Let's Go → Home → Tours & Attractions → Dunn's River Falls detail).

## Shared design system

All shared styles live in `assets/styles.css` — colors, type scale, buttons, chips, cards, and the phone device frame are defined once as CSS custom properties so every screen stays visually consistent. To restyle the whole app (e.g. adjust the green/gold palette), edit the `:root` variables at the top of that file.

## Images

Photos are pulled live from Unsplash (verified working URLs) as stand-ins for real vendor/location photography. Before shipping to production or the App Store, replace these with:
- Licensed or original photography of the actual tours/locations
- Compressed, properly sized assets bundled with the app (not hotlinked)

## Notes

- These are static prototypes for design/UX validation — no backend, booking, or auth logic is wired up.
- Built to slot into the Capacitor-wrapped native build described in `PATWAGO_V2_SPEC.md`.
- The device frame (`.device` in styles.css) simulates an iPhone viewport at 375×812 for preview purposes only; real screens should be fully responsive.
