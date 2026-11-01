# Image provenance

One block per committed generated asset (format: `references/art-direction.md`, "Provenance record").

## assets/icon.png
- Date: 2026-11-01
- Tool and model: Codex CLI image generation (built-in image_gen) / model id `not exposed`
- Seed: `not supported`
- Reference images: none
- Prompt (verbatim, from the original Codex icon-generation session's `content icon prompt` output, option B; the session adapted it as noted below the fence):

```text
[STYLE LOCK — completetech]
Clean glossy isometric 3D product illustration, orthographic isometric camera from the front-left. Every scene sits on one rounded-rectangle platform: deep navy (#001F3F) top, ink (#0F172A) sides, a thin glowing sky-blue (#00A7FD) edge line, floating above an empty background with a soft contact shadow. Objects are smooth satin plastic in sky blue (#00A7FD), azure (#0081ED), royal blue (#005ADD) and off-white (#F1F5F9), with small warm-gold (#FFC300) details. Glass parts are frosted translucent blue. Thin gold circuit traces ending in round solder pads link the objects across the platform top. Soft rounded geometry, subtle bevels, bloom on gold details only, key light from the upper left, calm and uncluttered.

[SUBJECT]
A curated stack of blank repository presentation cards, a blank terminal window and a magnifier that checks their alignment.

[OBJECTS]
Card stack, blank terminal window, magnifier.

[COMPOSITION]
Isolated platform and objects on a perfectly flat, untextured #F8FAFC background; no floor, grid, gradient or glow touching the edges; 10% empty margin on all sides. Square 1024x1024.

[PALETTE]
Use only these colors: #0F172A, #001F3F, #00A7FD, #0081ED, #005ADD, #FFC300, #F8FAFC, #F1F5F9, #64748B. Gold #FFC300 is for small details only.

[EXCLUSIONS]
No text, letters, numbers, symbols, words, labels, signatures, watermarks, logos, brand marks or interface text; every paper, screen and sign surface stays blank. No people, human faces or human hands. No photorealism, no clutter, no extra objects. No letters, typography, code, numbers, logos, marks or brand emblems. No check-mark symbols. Keep details bold enough to remain recognizable at 48 pixels.
```

- Prompt adaptations made for the Codex call (recorded by that session): request a single separate candidate per call (four calls); genuine transparency instead of the matte #F8FAFC ground; at least 16.5 percent margin with a central 688 pixel live area. The text of those adaptations is not available verbatim beyond this summary.
- Images requested: 1 per call (4 single-image calls, candidates 1 to 4); selected: 1 (candidate 1, the first candidate meeting the automated checks: no text, marks or people, clear card, window and magnifier silhouette at 48 px). Raw candidate sha256 `4511e310598f834befb90777f67bae4d26289545ad1354a05c1f79c72f94cdb7` (kept out of the repository).
- Post-processing: `showcase.py content icon normalize --ground transparent` at merged commit 04fbc0a (render verified at 6c31d31 in the exact-commit VM); output sha256 `a1bbf17b8f066ec7e8442a323d4b1a21656a8f8788a1e54ece6f83e76dde7bf5`; 54099 bytes (52.8 KB).
- Codex session: the session id and the generated-images file name were not recorded in the orchestration files available at commit time.
