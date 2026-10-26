# GitHub-safe SVG rules

These rules apply to every SVG the estate commits for a README or profile: the profile intro, repo cards, org tiles, the stack plate and dividers. **S** rules are checked statically by `showcase.py lint svg`. **R** rules need the optional render gate (Chromium). **D21** is the single-dark-asset rule from decision 21.

Decision 21 is already applied here: every surface ships as **one dark file** used on both GitHub themes. The former light/dark pair rule (S22), the light theme tokens (S24 light) and the profile kit's "every image needs a dark variant" rule are struck. The decision 18 footer logo is the only `<picture>` in the estate, and it swaps logo PNGs, not SVGs.

## 1. File and canvas

| ID | Rule |
|---|---|
| S01 | The file parses with a real XML parser. UTF-8, no BOM. |
| S02 | The root `viewBox` exactly matches the asset kind, and `width`/`height` equal the viewBox size. Kinds: intro `0 0 1280 320` (or `0 0 1280 360` when chosen); card `0 0 400 160` (embedded at `width="400"`, so 1 unit = 1 display px); tile `0 0 400 160`; plate `0 0 1280 320`; divider `0 0 1200 20`. A new kind needs an entry here first. |
| S03 | No `--` inside an XML comment (it blanks the whole image). A bare `&` is written `&amp;`. |
| S04 | The plate is opaque. Transparency is allowed only in the rounded-corner pixels outside the plate's `rx` (≤ 16). Text never sits directly on the GitHub page colour. |
| S06 | Never stroke an axis-aligned `<line>` with a gradient (its bounding box has zero area, so it paints nothing). Use a `<rect>` or `gradientUnits="userSpaceOnUse"`. |
| S07 | Output is deterministic: stable element order, fixed precision, no timestamps, absolute dates only. Rebuilding from unchanged data gives a byte-identical file. |

## 2. Fonts and text

| ID | Rule |
|---|---|
| S05a | Brand text is outlined to paths at build time (Poppins, JetBrains Mono, the T2 family fonts). Each glyph is one `<path id>` in `<defs>`, placed with `<use href>`; path data uses relative integers at 100 units/em; shaping uses HarfBuzz. Generated assets contain no `<text>`, `<tspan>` or `<textPath>`. |
| S05b | System-stack exception, hand-made one-offs only: `<text>` is allowed only if every family in its stack is a system or generic family, the layout leaves at least 15% width slack, and no web font is named first. The linter warns; an art reviewer signs it off. Generated estate assets never use it. |
| S05c | No `@font-face`, by URL or as a `data:` font. |
| S08 | Icons, arrows, ticks, stars and separators are drawn as paths. Symbol glyphs such as stars, arrows and check marks are not allowed, outlined or not. Ordinary punctuation inside a text run (`·`, `,`) is fine. |
| S09 | Text is never truncated or ellipsised. Sizes step down a fixed ladder, then wrap at spaces or hyphens; if it still does not fit, the build logs `art-fail` and writes nothing. Card ladders: name 21 → 19 → 17 → 16, then 2 lines; description 12.5 → 12 → 11.5, at most 3 lines. Optional items drop in this order: stars, language, attribute chips. The key chip is never dropped. |

## 3. Banned features

| ID | Rule |
|---|---|
| S05 | None of: `script`, `foreignObject`, `iframe`, `video`, `audio`, `canvas`, `a`, `font`, `font-face`. No `on*` attributes. No `xlink:href` (use SVG 2 `href`). |
| S05d | Every `href` is a fragment (`#id`) or `data:image/(png\|webp\|jpeg);base64,…`. Never an external or relative URL: SVG used as an image loads no subresources. Every `url(...)` points to a fragment. No `@import`. Data-URI media types are checked. |
| S12 | No `feTurbulence` or `feDisplacementMap`. |
| S14 | Nothing animates under or through a filter. Glow comes from radial-gradient fills, not `feGaussianBlur`. |
| S15 | Nothing in the image is meant to be clicked or copied. Every link, contact detail and number shown in the image is repeated as real Markdown next to it. |
| S16 | No liveness labels, no hand-typed numbers, no vanity stats. Counts that change (repository or org totals) go in Markdown, not in images. |

## 4. Animation

| ID | Rule |
|---|---|
| S11 | Only the **intro** kind may animate: one per page, on the personal profile and on T1 flagship orgs. Cards, tiles, plates and dividers are static. |
| S11a | CSS `@keyframes` for `opacity`, `transform` and `stroke-dashoffset` (trace draw-in with `pathLength="1"`, glyph reveal, caret with `steps(n)`); SMIL only where CSS cannot do the job (`animateMotion` with `<mpath href>`, synchronised `r`/`opacity` pulses). Never animate `d`, `stop-color`, filter attributes, `seed` or `baseFrequency`. |
| S11b | At t = 0 the plate, mark, eyebrow, name and chips are fully visible. Only the traces and the tagline start hidden. |
| S11c | Intro motion settles by 2.5 s (traces 0.2–1.4 s, tagline 0.6–2.2 s). After that exactly one perpetual system runs (signals on traces with their terminal pulses). A caret blink stops after at most 3 cycles. |
| S13 | Every perpetual loop is at least 4 s, and loop durations are not synchronised (6.1, 7.7, 9.3 s). Nothing flashes more than 3 times per second. No jitter or shake. |
| S13a | Signals move along a defined path and fade with `keyTimes`. A terminal pulse fires only when its signal arrives (same `dur` and `begin`, keyTimes after the arrival point). |

## 5. Reduced motion

| ID | Rule |
|---|---|
| S20 | Every animated SVG contains `@media (prefers-reduced-motion: reduce){.anim{display:none}.still{display:inline}}`, a `.still` group, and `.still{display:none}` by default. The `.still` group draws the settled frame: traces complete, tagline complete, caret solid, no signals. |
| S21 | Every SMIL element, and every element whose class carries a CSS `animation`, sits inside a `.anim` group. |
| R20 | The render gate launches Chromium with `--force-prefers-reduced-motion` (page-level emulation does not reach SVG images). At t = 0 the render must equal the `.still` frame. |

## 6. One dark design (decision 21)

| ID | Rule |
|---|---|
| D21 | One file per surface. A file named `*-dark.svg` or `*-light.svg` beside a sibling of the same stem is a FAIL. README embeds use a plain `<img>`, never `<picture>`, except the decision 18 footer. |
| S23 | No internal `prefers-color-scheme` theming inside an SVG. |
| S24 | Dark tokens only: the family canvas; text `#F1F5F9` / `#CBD5E1` on the CompleteTech canvas; eyebrow sky `#00A7FD` (6.27:1 on navy); edge hairline sky at 28–30%. The gold key chip is `#FFC300` with `#0F172A` text; attribute chips are `#005ADD` with `#FFFFFF` text. The card's icon tile uses the light `card_fill`, matching the banner's white card, so one icon file serves both. |

## 7. Size budgets

| ID | Rule |
|---|---|
| S10 | Hard limits and targets: intro ≤ 300 KB hard, ≤ 120 KB target; card or tile ≤ 40 KB hard, ≤ 30 KB target; stack plate ≤ 150 KB; divider ≤ 4 KB; a GIF fallback ≤ 1 MB and only if an animated SVG is refused. Embedded rasters are WebP at 2× display size, quality 82–86. A whole profile page (intro and 12 cards) stays ≤ 600 KB. |
| S10a | Never wrap a raster in an SVG unless the SVG adds vector text or motion. |

## 8. Accessibility and legibility

| ID | Rule |
|---|---|
| S30 | The root has `role="img"` and an `aria-label`, plus a `<title>` with identical text. |
| S31 | Animated assets carry a `<desc>` that describes the motion and lists every text string. |
| S32 | The Markdown `alt` is the accessible name. Intro: name, company and tagline. Card: `REPO: DESCRIPTION` verbatim. |
| S33 | Every text and background token pair has contrast of at least 4.5:1, or the build logs `art-fail`. |
| R12 | Legible at a 390 px viewport: intro name ≥ 56 px and tagline ≥ 30 px; card description ≥ 11 px and name ≥ 16 px at 400 px display. Smaller labels (eyebrows, chips) are texture only, and their facts must also appear in Markdown. |

## 9. Marks and brand

| ID | Rule |
|---|---|
| S40 | Marks are embedded only from committed brand files (`assets/brand/`, the org mark, or the repository's own `assets/icon.png`), unaltered: no cropping, masking, recolouring or redrawing. Traces start at pads outside the mark and never redraw its circuitry. |
| S41 | Colours come only from the family tokens. Gold is used only for traces, pads, the key chip and the prompt chevron. |

## What `lint svg` checks

```text
showcase.py lint svg --kind intro|card|tile|plate|divider FILE...
```

1. Parse (S01), then S02 viewBox, width and height, and the S10 budget (FAIL over the hard limit, warn over the target).
2. S03 comments; banned elements S05, S05a, S12; `on*` and `xlink:*` attributes.
3. Every `href` and `url(...)` (S05d), data-URI media types, no `@import` or `@font-face`.
4. S06 gradient-stroked lines; S08 symbol code points in `aria-label` and `<desc>`.
5. Animation: FAIL unless the kind is `intro` (S11); the S20 media rule, a `.still` group, S21 `.anim` ancestry, loops of at least 4 s (S13), S13a pulse timing, a `<desc>` (S31, warning).
6. S30 `role`, `aria-label` and `<title>`; S14 nothing animated under a filter.
7. D21 single dark asset.

Output is one JSON line per file: `{file, result: PASS|FAIL, fails[], warns[], bytes, animated}`. Exit 1 on any FAIL.

## Render gate (optional, Chromium)

1. Deterministic frames: pause every animation and seek to t = 0, 1.0, 6.3 and 30 s; capture at device pixel ratio 2. Never sleep and screenshot. At t = 0, the name and eyebrow boxes differ from t = 30 by at most 0.5%.
2. Reduced motion: embed as `<img>` in a browser launched with `--force-prefers-reduced-motion`; the load capture matches the t = 30 frame without the signal layer (at most 1% pixel difference).
3. Golden diff: each card and intro against its approved golden render (at most 0.5% of pixels at ΔE > 6).
4. Contact sheet: a GitHub-like page (`#ffffff` and `#0d1117`) at 1012 px and 390 px; a human signs off on the set.
5. Performance, intro only: main-thread busy at most 10% over 10 s.

Pilot checks that need github.com itself: the `<a><picture>` footer in both themes, CSS keyframes, SMIL and the reduced-motion swap in Safari and Firefox, and WebP `data:` images inside SVG in Safari.
