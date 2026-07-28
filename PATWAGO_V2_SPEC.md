# PatWaGo V2 — App Store Edition
### Complete Product Specification · Jamaica Travel Companion
**Target:** Apple App Store (iOS 16+) · Google Play (Android 10+)
**Prepared:** 2026-07-28

---

## Table of Contents
1. [What Changed From V1](#1-what-changed-from-v1)
2. [Apple App Store Compliance](#2-apple-app-store-compliance)
3. [Guardian Mode — Safety System Redesign](#3-guardian-mode--safety-system-redesign)
4. [Feature Specifications](#4-feature-specifications)
5. [UI/UX & CRO Improvements](#5-uiux--cro-improvements)
6. [Monetization & Pricing](#6-monetization--pricing)
7. [Technical Stack](#7-technical-stack)
8. [App Store Submission Checklist](#8-app-store-submission-checklist)
9. [Target Scores After V2](#9-target-scores-after-v2)

---

## 1. What Changed From V1

### Removed
| Item | Reason |
|------|---------|
| Admin credentials (`admin/patwago`) exposed on site | Security breach, instant trust killer with cold traffic |
| "Admin Center" in main navigation | Signals pre-launch product to every first-time visitor |
| One-tap SOS button (as previously designed) | Apple Guideline 1.4 / 5.1.1 — redesigned as Guardian Mode |
| Feature request form on homepage | Signals roadmap gaps to cold traffic |
| Triple CTA in hero ("Try Demo" + "Start free" + "Get the app") | Fragments intent, kills conversion |
| Generic star rating (4.9 ★, no count) | Indistinguishable from a fake placeholder |

### Replaced / Improved
| V1 | V2 |
|----|----|
| One-tap SOS | Guardian Mode (full safety coordination system — App Store compliant) |
| "Admin Center" in nav | Admin dashboard at `admin.patwago.com` — no public link |
| 3 hero CTAs | 1 primary CTA: **"Start free — no card needed"** |
| Bare star rating | Real testimonials with name, origin, trip type |
| Feature request form | Post-onboarding feedback flow (in-app only) |
| Static emergency number list | Contextual emergency info card with native-dialer deep links |
| Web-only app | Native hybrid (Capacitor/React Native) for App Store submission |

---

## 2. Apple App Store Compliance

### 2.1 Guideline 1.4 — Physical Harm
**Rule:** Apps must not put users in harm's way. Emergency features must be clearly scoped and cannot simulate or replace emergency dispatch services.

**V2 Approach:**
- The SOS button is completely removed.
- Emergency calling is handled via **pre-configured native phone dialer deep links** (`tel:119`, `tel:110`, `tel:888-526-7651`). Apple explicitly permits this — the user's native dialer handles the call, not the app.
- A permanent disclaimer reads: *"PatWaGo is not an emergency service. In a life-threatening emergency, call 119 (Jamaica Police) or 110 (Ambulance)."*
- Safety features are repositioned as **coordination tools between travelers and their trusted contacts** — not a replacement for official emergency services.

### 2.2 Guideline 5.1.1 — Location Data
**Rule:** Apps collecting location must explain clearly why, and collect only what is necessary. Background location requires explicit justification.

**V2 Approach:**
- Location is used for: (a) vendor proximity search, (b) offline map center, (c) Guardian Mode check-in sharing.
- Background location is requested **only** when Guardian Mode is active, with a plain-language explanation at the prompt: *"PatWaGo uses your location in the background to send check-in updates to your Guardians while Guardian Mode is on. Turn off Guardian Mode to stop location sharing."*
- Location data is never stored server-side beyond the duration of an active Guardian Mode session.
- Full disclosure in App Store Privacy Nutrition Label: Location (Precise), Usage Data, User Content.

### 2.3 Guideline 3.1.1 — In-App Purchases
**Rule:** Digital goods sold within an iOS app must go through Apple's IAP system. External payment links for digital goods are prohibited inside the app (web is exempt).

**V2 Pricing Adjustments (accounting for 30% Apple cut):**

| Plan | Web Price | App Price (IAP) | Net Revenue |
|------|-----------|-----------------|-------------|
| Day Pass | $9.99 | $12.99 | ~$9.09 |
| Trip Pass (7 days) | $29.99 | $39.99 | ~$27.99 |
| Verified Vendor | $29/mo | Web-only checkout | $29/mo (full) |
| Pro Vendor | $79/mo | Web-only checkout | $79/mo (full) |

**Note:** Vendor subscription plans are sold exclusively through the web (`patwago.com/vendor-signup`) to avoid the 30% cut. Inside the app, a screen directs vendors to the website — Apple permits this for physical goods / B2B services, and vendor plans qualify under their guidelines. Confirm with Apple's Small Business Program if volume qualifies for 15% cut on consumer IAP.

### 2.4 Guideline 4.2 — Minimum Functionality
**Rule:** Apps must not be simple web wrappers. They must offer meaningful native functionality.

**V2 Native Features (non-negotiable for approval):**
- Offline Patois phrase library (SQLite bundle, no network required)
- Offline map tiles for major Jamaica parishes (cached on install)
- Push notifications (safety check-ins, vendor booking confirmations)
- Native share sheet integration (share location, share vendor)
- Haptic feedback on key interactions (SOS-adjacent, booking confirmation)
- Siri Shortcuts: "Ask Siri to ask Yaadie about getting around Kingston"
- Home Screen Widgets: Guardian Mode status, next check-in timer

### 2.5 Guideline 2.1 — App Completeness
**Rule:** Apps submitted must be production-ready. No placeholder content, no demo credentials, no unfinished flows.

**V2 Requirements:**
- Admin dashboard completely removed from the app and the public website nav.
- All demo flows replaced with real data or clearly labeled sandbox mode (only accessible to internal testers via TestFlight entitlement, not the public build).
- Every navigation item must lead to a complete screen before submission.

### 2.6 Voice Data (Patois Translator)
**If** the translator records audio and sends it to a server for processing, this triggers Apple's sensitive data policies.

**V2 Approach:** Use on-device speech recognition via Apple's `SFSpeechRecognizer` API for voice input. Only the transcribed text (not the audio file) is sent to the translation API. This keeps the app out of the "audio recording" sensitive category.

---

## 3. Guardian Mode — Safety System Redesign

Guardian Mode replaces the previous "one-tap SOS" with a travel safety coordination system. It is explicitly **not** an emergency service — it is a peer-to-peer safety check-in system, similar to bSafe, Life360, or Google's Trusted Contacts app, all of which pass App Store review.

### How It Works

**Setup (one-time):**
1. Traveler nominates 1–3 "Guardians" (family or friends back home) by phone number or email.
2. Guardians receive an SMS/email invitation to PatWaGo Guardian — a free companion web app (no app install required for Guardians).
3. Traveler sets their trip dates and an optional daily check-in schedule.

**Active Session:**
- When the traveler turns on Guardian Mode, their Guardians see a live "Online" status and their general area (parish-level, not street-level, by default).
- Traveler can **voluntarily share precise location** at any time with a one-tap "Share my location now" button → sends a native iMessage/WhatsApp deep link with a Google Maps URL.
- Traveler can set a **check-in timer**: "Check in with my Guardians in 2 hours." If they miss it, Guardians receive an automatic alert: *"[Name] missed their scheduled check-in at 3:00 PM. Their last known location was Negril, Westmoreland."*
- A prominent **"I'm Safe" button** is always visible during an active session — one tap resets the timer and notifies Guardians.

**Emergency Screen (Apple-compliant):**
- A dedicated "Emergency" tab shows local emergency numbers as native-dialer buttons.
- Each button opens the iOS/Android native phone dialer pre-filled — the app never makes the call itself.
- Numbers shown: Jamaica Police (119), Ambulance (110), Tourist Police (888-526-7651), US Embassy Kingston, Air Ambulance (for medical evacuation info).
- STEP Program: a link that opens the US State Department enrollment page in Safari (not an in-app webview).
- Clear header on this screen: *"In an emergency, call these numbers. PatWaGo will open your phone's dialer."*

**Why This Passes App Store Review:**
- No fake 911 dispatch. No emergency service simulation.
- All actual calls go through the native phone dialer — Apple explicitly permits `tel:` URL schemes.
- The safety coordination (check-ins, location sharing) is peer-to-peer, not to emergency services.
- Similar apps (bSafe, Life360, Trusted Contacts) have shipped on the App Store for years under this model.

---

## 4. Feature Specifications

### 4.1 Onboarding Flow (New)
Cold traffic and App Store downloads need a fast, low-friction path to value.

**Screen 1 — Welcome:**
Single screen. Headline: *"Jamaica in your pocket."* Subhead: *"Translate, book, explore — safely."*
Two options: "Start free (no card)" / "I have an account."

**Screen 2 — Quick Setup (3 taps):**
- What brings you to Jamaica? → Solo trip / Couple / Family / Group
- Which area? → Dropdown of parishes + "Not sure yet"
- When? → Date picker (used to show relevant seasonal safety alerts and vendor availability)

**Screen 3 — Guardian Mode Prompt:**
*"Want a safety net while you explore?"* Brief explanation of Guardian Mode. "Set up now (takes 60 seconds)" / "Maybe later."

**Screen 4 — Home.**

**No email required to start.** Email/account creation is deferred to the first booking or when Guardian Mode is activated — both natural moments of commitment.

### 4.2 Patois Translator (Upgraded)
**V2 Changes:**
- **Offline phrase library** (500+ phrases bundled with app, no network required) — organized by category: Greetings, Food, Transport, Prices, Emergencies, Directions.
- **Voice input** via native speech recognition (on-device, no audio sent to server).
- **Voice output** (text-to-speech for both English and Patois) — lets the traveler play the phrase for a local vendor.
- **Keyboard extension** (iOS/Android) — traveler can use the Patois translator in any messaging app, including WhatsApp.
- **Pronunciation guide** — phonetic spelling shown below every translation.
- **Phrasebook** — save frequently used phrases for quick re-use offline.

### 4.3 Vendor Marketplace (Upgraded)
**V2 Changes:**
- **Map-first layout** — vendors appear as pins on an offline-capable map before a list view. Cold-traffic visitors understand the density of verified vendors immediately.
- **Price transparency upfront** — every vendor listing shows a fixed-rate or price range on the card, not hidden behind a tap.
- **"Verified" badge explained** — on first encounter, a tooltip explains what verification means (ID checked, background reviewed, insured). This is the scam-prevention pitch made visible.
- **Booking confirmation push notification** — native push, not just email.
- **Review gating** — only users who completed a booking can leave a review. "Verified booking" badge on every review.
- **Vendor photos** — minimum 5 photos required for any listing. Users can add their own photos post-trip.

**Categories (unchanged from V1, confirmed correct):**
Food · Water Sports · Tours · Adventure · Transport · Beauty · Crafts · Lodging

### 4.4 Yaadie AI Concierge (Promoted)
Yaadie goes from a background mention to a primary interface element.

**V2 Changes:**
- **Persistent floating button** on every screen except checkout and emergency — one tap opens Yaadie.
- **Contextual awareness** — Yaadie knows the user's current location (if permitted), their booked vendors, and their travel dates. Answers are relevant, not generic.
- **Offline cached responses** — the 50 most-asked Jamaica travel questions are cached locally. Yaadie can answer "How much should a taxi from Kingston Airport cost?" even with no signal.
- **Natural language booking** — "Find me a snorkeling tour near Negril for tomorrow under $80" → Yaadie returns matching vendors with a one-tap booking option.
- **Yaadie on the web** — a live demo widget on `patwago.com` (not the full concierge, but a 3-question demo) serves as a conversion hook for cold web traffic.

### 4.5 GPS Maps (Upgraded)
- **Offline tile download** by parish — user selects which areas to cache before traveling (critical when roaming data is expensive).
- **Vendor layer** — toggle verified vendors on/off as a map overlay.
- **Fixed taxi route overlays** — common airport-to-resort routes shown with the official fixed price. Makes scam pricing instantly visible.
- **Community report pins** — community safety alerts appear as pins on the map (see 4.6).

### 4.6 Community Safety Alerts (Upgraded from V1)
- **Waze-style reporting** — travelers tap to report: Road blocked / Price scam / Unsafe area / Other.
- **Time-decay algorithm** — reports older than 6 hours are automatically muted unless corroborated by a second report.
- **STEP integration** — US State Department Level alerts for Jamaica appear as a banner when active.
- **Parish-level safety summary** — each parish gets a simple traffic-light status (Green / Yellow / Red) updated from community reports + STEP data.

### 4.7 Home Screen Widgets (New — Native Differentiator)
- **Guardian Mode Widget** — shows "Guardian Mode: Active · Check-in in 1h 43m" with an "I'm Safe" tap target. Makes the safety system ambient, not something users have to remember to open.
- **Today Widget** — shows booked vendors for the day, local time, and current parish safety status.

---

## 5. UI/UX & CRO Improvements

### 5.1 Website Hero (patwago.com)
**Before:**
```
Headline → Sub → [Try Demo] [Start free trial] [Get the app]
4.9 ★ (no count)
```

**After:**
```
Headline: "Jamaica without the guesswork."
Sub: "Translate Patois, book verified locals, stay safe — all in one app."
[Start free — no card needed]  ← single CTA
4.9 ★ from 312 travelers  ← real count
```

### 5.2 Social Proof Block (New section, add above pricing)
Three testimonial cards. Format:
```
"The taxi pricing alone saved me from getting ripped off at the airport.
I saw the fixed rate in the app and showed it to the driver."
— Marcus T., Atlanta GA · Solo trip, 7 days
```
Source from beta users. Photo optional but increases conversion ~30%.

### 5.3 Page Section Order (Reordered for cold traffic)
1. Hero + single CTA
2. Social proof (testimonials)
3. **Safety section** (moved up — this is the anxiety-reducer for cold traffic)
4. Features (Translator, Marketplace, Yaadie, Maps)
5. Pricing
6. Vendor section
7. Footer

### 5.4 Navigation (Cleaned)
**Before:** Features · How it works · Pricing · Safety · Vendors · Become a Vendor · **Admin Center**

**After:** Features · Safety · Pricing · Vendors · Become a Vendor

Admin tooling: accessible only at `admin.patwago.com`, no public link anywhere.

### 5.5 Vendor Signup CRO
- Replace: *"Fill this out and we'll get you onboarded within 24 hours."*
- With: *"Most vendors are live and searchable within 2 hours of submitting."*
- Add: vendor count display — *"Join 47 verified businesses already on PatWaGo."*
- Add: one vendor testimonial above the form.

---

## 6. Monetization & Pricing

### Consumer Tiers
| Plan | Web | iOS/Android IAP | Duration |
|------|-----|-----------------|----------|
| Free trial | $0 | $0 | 24 hours |
| Day Pass | $9.99 | $12.99 | 24 hours |
| Trip Pass | $29.99 | $39.99 | 7 days |
| Annual (new) | $79/yr | $99.99/yr | 365 days |

**Annual plan rationale:** Captures expats living in Jamaica, frequent visitors, and travel agents. $79/yr is a no-brainer for anyone visiting more than 3 times.

### Vendor Tiers (Web-only checkout to preserve margin)
| Plan | Price | Key Features |
|------|-------|-------------|
| Starter | Free | Listed, searchable, reviewable |
| Verified | $29/mo | Verified badge, priority placement, in-app booking |
| Pro | $79/mo | Featured placement, analytics, API, multi-staff, ad credits |

### New Revenue Streams (V2)
- **Commission model (optional):** Offer vendors a commission-based plan (0$/mo + 8% per booking) as an alternative to Verified. Lowers barrier to entry for new businesses.
- **Featured placement ads:** Sell rotating "Featured Today" slots to Pro vendors — $15-25/day. Low lift, direct revenue.
- **Guardian Web App (B2C premium):** Guardians (family at home) can pay $2.99/mo for real-time location instead of parish-level updates. Upsell to worried parents of solo travelers.

---

## 7. Technical Stack

### Recommended Approach: Capacitor (fastest path to stores)
If the current site is built in React/Vue/plain HTML, **Capacitor** wraps the web app in a native shell with access to native APIs. This is the fastest path to App Store submission while preserving existing code.

```
Web app (existing)
  + Capacitor shell
  + Native plugins:
      @capacitor/geolocation       → Guardian Mode location
      @capacitor/local-notifications → check-in reminders
      @capacitor/push-notifications → booking confirmations
      @capacitor/speech             → Patois voice input
      @capacitor/haptics            → booking/safe-tap feedback
      @capacitor/share              → native share sheet
      @capacitor-community/sqlite   → offline phrase library
      capacitor-background-runner   → Guardian Mode background task
```

**Alternative:** React Native (Expo) if a full rewrite is acceptable. Higher quality native feel, longer timeline (8–12 weeks vs 4–6 weeks for Capacitor).

### Backend Requirements (for new V2 features)
- **Guardian Mode session state:** Real-time location updates → use Supabase Realtime or Firebase.
- **Push notifications:** OneSignal (simplest) or native APNs/FCM directly.
- **Offline maps:** Mapbox GL offline tiles (already works with Capacitor).
- **Patois phrase SQLite bundle:** Build the DB as a static asset bundled with the app. No network required.
- **Yaadie AI:** If using Claude API — cache the top 50 Q&A pairs locally for offline mode.

### Background Location (Guardian Mode)
- iOS requires the `NSLocationAlwaysAndWhenInUseUsageDescription` key in `Info.plist`.
- Add `UIBackgroundModes: location` to enable background updates.
- Capacitor's `@capacitor/geolocation` handles this with the `enableHighAccuracy` and `timeout` options.
- Use significant-location-change mode (not continuous GPS) to preserve battery. Accuracy is sufficient for parish-level updates.

---

## 8. App Store Submission Checklist

### Pre-Submission (Must Complete)
- [ ] Remove all public admin credentials and admin nav links from patwago.com
- [ ] Enroll in Apple Developer Program — `developer.apple.com` ($99/yr, 1–3 days to process)
- [ ] Enroll in Google Play Console — `play.google.com/console` ($25 one-time)
- [ ] Choose tech stack (Capacitor recommended) and scaffold the native project
- [ ] Implement Guardian Mode per spec in Section 3 (replaces SOS)
- [ ] Add the Emergency Screen with native `tel:` deep links (no in-app calling)
- [ ] Add the disclaimer: *"PatWaGo is not an emergency service…"* on Guardian and Emergency screens
- [ ] Bundle offline Patois phrase library (SQLite)
- [ ] Set up Apple IAP for Day Pass ($12.99) and Trip Pass ($39.99)
- [ ] Audit vendor plan checkout — confirm it routes to web, not IAP
- [ ] Build App icon: 1024 × 1024px, no transparency, no rounded corners, legible at 60px
- [ ] Write App Store description (4000 chars max) — lead with Patois translation, safety, verified vendors
- [ ] Create 5 screenshots per device size (iPhone 6.7", 6.5", iPad 12.9")
- [ ] Complete App Store Privacy Nutrition Label (Location, Usage Data, User Content)
- [ ] Review `Info.plist` usage description strings — must be specific, not generic
- [ ] Run TestFlight beta with minimum 20 real users, including Jamaica-based testers
- [ ] Verify all navigation paths reach complete, non-placeholder screens
- [ ] Confirm push notification flows work end-to-end on a real device
- [ ] Review Apple's Small Business Program eligibility (15% cut if under $1M annual revenue)

### App Store Listing Copy
**App Name:** PatWaGo — Jamaica Travel App

**Subtitle (30 chars):** Translate, Book, Stay Safe

**Keywords (100 chars):** jamaica,travel,patois,translator,safety,tours,transport,booking,concierge,offline

**Description (first 255 chars — shown before "more"):**
*Your Jamaica companion — all in one app. Translate Patois in real time, book verified local experiences, navigate with offline GPS, and travel safely with Guardian Mode check-ins. No scams. No guesswork.*

### Common Rejection Reasons to Pre-Empt
| Risk | Mitigation |
|------|-----------|
| Emergency feature rejection | Guardian Mode + disclaimer; all calls via native dialer |
| Web wrapper rejection | Native plugins for location, notifications, haptics, share |
| Metadata mismatch | Screenshot every featured capability before submission |
| IAP bypass | Vendor plans explicitly offered web-only; note in app metadata |
| Privacy label gaps | Audit every API call for data collection before submission |

---

## 9. Target Scores After V2

| Dimension | V1 Score | V2 Target | Key Changes |
|-----------|----------|-----------|-------------|
| CRO (cold traffic) | 52/100 | **88/100** | Single CTA, real testimonials, safety first, admin removed |
| Cold Traffic Readiness | 41/100 | **85/100** | Trust signals, social proof, no pre-launch signals |
| App Store Readiness | 22/100 | **95/100** | Full compliance checklist, Guardian Mode, native features |
| Vendor Signup CRO | 65/100 | **85/100** | Vendor count, testimonials, faster onboarding promise |
| Security | 40/100 | **95/100** | Credentials removed, admin gated, privacy policy reviewed |

### What Gets You to 95+ on App Store Submission
1. Guardian Mode over SOS (biggest risk eliminated)
2. Real native features (offline maps, offline phrases, push notifications, widgets)
3. IAP for digital goods, web-only for vendor subscriptions
4. Clean, complete UX with no placeholder screens
5. Accurate, specific privacy descriptions in every OS permission prompt
6. TestFlight beta with real Jamaica-based users before submission

### The 5% You Can't Fully Control
Apple's review is human-operated and inconsistent. Even compliant apps sometimes get an initial rejection for minor reasons. Plan for one revision cycle. Common first-rejection reasons that resolve quickly: missing screenshot for a specific device size, overly brief usage description string, or a reviewer testing an edge-case empty state that wasn't polished. None of these are blocking — they just require a resubmit.

---

*PatWaGo V2 Spec · Prepared 2026-07-28*
