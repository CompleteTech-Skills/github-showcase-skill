# Art direction

Condensed from `ct-std-v1` §9 with decisions 12, 13, 19 and 21 applied. It covers what image agents may draw (illustrations only), the family palettes and motifs, asset sizes and the art QA checklist. The generators in this skill typeset every word and place every mark; the image model never draws text, logos or marks.

`references/brand.yaml` is what the generators render. The tables below document the same values for people and prompts; when they disagree, `brand.yaml` wins and the difference is a bug to report.

## Pipeline rules (MUST)

1. **The image model draws only illustration layers.** Never text, letters, numbers, logos or brand marks.
2. **Marks come only from committed files.** Never crop, mask, recolour or redraw a mark. The only crops ever made are the one-time `mark-dark.png`, `bulb-dark.png` and `jev-reference.png`, made by the estate planner on the chosen master (decision 19: re-measure on the new master; never reuse old pixel coordinates).
3. **All text is typeset by the compositor** with real fonts: Poppins and JetBrains Mono for CompleteTech (both OFL); T2 families use their own fonts.
4. **One style lock per family**, verbatim. Use the same model and version for a family run; record a seed only when one was requested (`content icon prompt --seed N`; otherwise "not supported"). Family seeds, for runs that choose to request one: CompleteTech `1025`, Jev-Engineering `3001`, jevplay-games `3101`, LibreEvolve `4001`, TouchedByAnAgent `5001`, romgenie `6001`.
5. **Pilot first, per family.** The user approves the first banner and card of each family before the rest are generated; they become the family's golden references.
6. **Every in-scope repository gets its own icon** (decision 12), `assets/icon.png`; watching-org forks are the only exception. T3 art waits for co-owner sign-off.
7. **Selection:** run the one-image prompt as four single-image invocations (each invocation is one candidate), reject any that fails the QA checklist, select the first remaining one in generation order with a one-line reason. If none passes, run four more single-image invocations once; then log `art-fail`.
8. **Mascot:** every jevplay-games prompt uses exactly `jevplay-games/.github/profile/assets/jev-reference.png`.
9. **No third-party IP:** no Pokémon creatures or Poké Balls, Among Us crewmates, Discord, Zoho or NetScaler logos, Hasbro board designs, real people, or anything sexual or suggestive.
10. **One dark design** (decision 21): banners, cards, tiles and intros ship one dark file used on both GitHub themes.

## Family palettes and motifs

| Family | Canvas | Primary | Accent | Text | Motif | Fonts |
|---|---|---|---|---|---|---|
| CompleteTech | ink `#0F172A` → navy `#001F3F`, 32 px `#1E3A8A` grid at 25% | sky `#00A7FD` → azure `#0081ED` → royal `#005ADD` | gold `#FFC300` (small details only); rose `#E11D48` only on the single finding object in Security art | `#F1F5F9`, `#CBD5E1`; muted `#94A3B8` | Isometric platform with satin-plastic objects linked by gold circuit traces | Poppins, JetBrains Mono |
| AI Ascension | ink `#15120E` / `#2A241C` | amber `#F2B75C` / `#E39B3A` | paper `#EDE4D3` | `#EDE4D3` | Existing system; banners kept | Fraunces, Bricolage Grotesque, JetBrains Mono |
| Jev Engineering | near-black `#010104` | cyan `#22D3EE`* | violet `#8B5CF6`* | `#F1F5F9` | A glowing central node fanning into lanes ending in a circle, square, triangle and diamond | Poppins, JetBrains Mono |
| jevplay.games | pink `#F386A1` with a halftone layer (12 px pitch, `#E551BA` at 20%) | magenta `#E551BA` | ink `#1E1E1E`, white | `#1E1E1E` | Retro pixel desktop windows and Jev, the boxy pixel robot | Existing wordmark; Press Start 2P (36 px or larger) |
| LibreEvolve | dark navy `#021527` | emerald `#10B981`* | faded emerald `#065F46`* | `#F1F5F9` | A lineage tree: most branches fade, one bright path continues | Poppins |
| Touched By An Agent | maroon `#1D1116` | amber `#F59E0B`* | magenta `#E11D74`* | `#FDF2F8` | One stylized robotic hand, signal ripples, a smart ring | Poppins |
| romgenie | dark teal `#002C31` | brass `#B8860B`* | lamp glow `#F4C430`* | `#F8FAFC` | Glossy 3D vault objects: chests, tapes, reels; a brass telescope and binoculars for the watching org | Poppins |

Starred values are approximate until the estate planner re-measures them and publishes `ct-std-v1.1`; families with starred values are `measured: false` in `brand.yaml`, and the generators refuse them without `--allow-unmeasured`.

**Banner and card tokens, CompleteTech:** eyebrow `#00A7FD`, title `#F1F5F9`, subtitle `#CBD5E1` (the golden's measured subtitle, 11.2:1 on navy), light card `#F8FAFC` (the golden's measured white), gold key chip `#FFC300` with `#0F172A` text, attribute chip `#005ADD` with `#FFFFFF` text, bottom bar `#005ADD`. Contrast: white on royal 5.99:1, ink on gold 11.1:1, sky on ink 6.75:1, sky on navy 6.27:1, muted on navy 6.46:1.

## CompleteTech org motifs (banner and shared card illustration)

| Org | Motif objects |
|---|---|
| CompleteTech-LLC | cloud puff, blank document sheet, gear, chat bubble |
| CompleteTech-Skills | envelope with open flap, document sheet with blank ruled lines, coin stack, scroll with gold wax seal, certificate with gold ribbon rosette |
| CompleteTech-LLC-AI-Research | telescope aimed at a cluster of glowing node spheres |
| `CompleteTech-Security` | shield over rack server units, blank tag cards; one tag card in `#E11D48` as the finding |
| CompleteTech-Infrastructure | rack server unit, plug-in cube, cloud puff, circuit board |
| CompleteTech-Commerce | bar-chart panel, coin stack, briefcase, magnifier |
| CompleteTech-Creative | film reel, microphone, open book, chat bubble |
| CompleteTech-Pokemon | card stack, game controller, coin stack |
| CompleteTech-Data | database cylinder stack, map pin, bar-chart panel, folder |
| CompleteTech-Games | puzzle piece, game controller, card stack |
| CompleteTech-Directories | folder, map pin, magnifier, certificate with gold ribbon rosette |
| CompleteTech-Hardware | circuit board, gear, plug-in cube |
| CompleteTechDiscord-Games | chat bubble, game controller, puzzle piece |
| CompleteTech-DiscordApps | chat bubble, plug-in cube, bar-chart panel |
| CompleteTech-Patent-IP | blank document sheet, gold wax seal, magnifier |
| CompleteTech-Career-Toolkit | blank document sheet, briefcase, certificate with gold ribbon rosette |
| CompleteTech-ManageEngine | chat bubble, folder, cloud puff, gear |

**Object library** (a new object needs user approval): blank document sheet, document sheet with blank ruled lines, envelope with open flap, certificate with gold ribbon rosette, gold wax seal, scroll, coin stack, check-mark seal, shield, rack server unit, database cylinder stack, gear, chat bubble, blank terminal window, bar-chart panel, magnifier, folder, cloud puff, plug-in cube, key card, blank tag card, map pin, circuit board, microphone, film reel, open book, game controller, puzzle piece, card stack, telescope, glowing node sphere, briefcase.

## Asset specification

| Asset | Path | Pixels | Format and limit |
|---|---|---|---|
| README hero banner | `docs/images/banner.png` | 1280×360 (or 2560×720) | PNG ≤ 300 KB, opaque; generated by `banner` |
| Repo card | `docs/images/card.svg` | 400×160 | SVG ≤ 40 KB; generated by `card` |
| Repository icon | `assets/icon.png` | 1024×1024 | PNG RGBA, transparent (drawn to read on the family card colour, `#F8FAFC` for CompleteTech) or with one opaque square ground (it then fills the card, full-bleed), ≤ 300 KB, no text |
| Brand files | `assets/brand/` in this repository (the published masters the generators and the footer use): `logo.png`, `logo-dark.png` (the exemplar pair), `logo-dark-full.png` (the candidate dark master, decision 19) and `mark-light.png`. `mark-dark.png` and `bulb-dark.png` are not shipped yet (see `assets/brand/README.md`). The former `CompleteTech-LLC/.github/brand/` location is historical only: those URLs returned 404, and the footer serves the files from `assets/brand/` (same sha256). | as committed | PNG; see `assets/brand/README.md` for modes |
| Logo pair in Skills repositories | `assets/logo.png`, `assets/logo-dark.png` | byte-identical to the `assets/brand/` masters (same sha256) | sha256 `a5c3c4ef55336ed4b883d3bc3bb6e1e942b836469bd2b2933bc8cc230b321621` (logo.png, 243,500 B) and `0dc00c0e5159518ff1d552b7052293b4e545ddd35be489e6d114e3ea64db27ec` (logo-dark.png, 210,785 B) |
| Social preview | `assets/social-preview.png` | 1280×640 | PNG ≤ 900 KB (heavier: JPG q85); hard limit under 1 MB; uploaded in the browser |
| Org avatar | `.github/profile/assets/avatar-500.png` (+ `avatar-1024.png` master) | 500×500 | Opaque PNG ≤ 300 KB; uploaded in the browser |
| Org banner | `.github/profile/assets/banner.jpg` | 1600×400 | JPG q85 ≤ 400 KB |
| Diagram source | `assets/diagrams/workflow.mmd` | — | Mermaid |
| Example preview | `assets/examples/example.png` | ≤ 2600 px wide | ≤ 600 KB |
| Screenshot (B, E) | `assets/screenshot.webp` | 1600×1000 viewport | WebP q80 ≤ 300 KB; captured from the live URL in a browser, never drawn by an image model |
| Provenance | `assets/PROMPTS.md`, `.github/profile/assets/PROMPTS.md` | — | Markdown, one block per committed generated asset |

## Codex image-generation recipe

### Command

The prompt comes from `content icon prompt` (written with `--out`, for example `art/prompts/ORG/REPO/icon.md`); give it to Codex non-interactively:

```bash
codex exec --skip-git-repo-check --json "$(cat art/prompts/ORG/REPO/icon.md)" > run.jsonl
```

- `exec` runs one non-interactive turn.
- `--skip-git-repo-check` lets it run from a scratch directory.
- `--json` prints one JSON event per line, so the run output can be parsed (the image path is read from it, see below).
- `--sandbox MODE` selects the sandbox policy for model-generated shell commands.
- `--output-last-message FILE` also writes the final message to FILE.
- A prompt of `-` is read from standard input.
- Each invocation runs one single-image prompt (`content icon prompt` asks for one image) and fills at most one candidate slot, but its output may report more than one path (for example an unreadable sandbox copy and a readable `generated_images` file). The candidate for the slot is the first readable path the run reported, see item 5 below.
- `codex exec --help` and CLI help only document flags; they do not prove that an image is generated. Only a returned readable image path proves a generation.

Use the same model and version for a whole family run (pipeline rule 4). Record the tool, model id and version in `PROMPTS.md` exactly as the run reports them; if the run does not expose a model id, write `not exposed` in the `TOOL / MODEL ID AND VERSION` field. Never invent a model id. Flag names follow codex-cli 0.166.0 at the time of writing; if one is rejected, run `codex exec --help` and change nothing else in the recipe.

This recipe does not rely on a documented image path: OpenAI documentation covers non-interactive `codex exec` and its JSON events, not where generated images are stored, so always use the exact path returned by the run output.

### Read the image path from the run output

1. After the run, search the `run.jsonl` events (or the final message) for the image file path Codex reports for the generated image, and use exactly that path (see item 5).
2. Never pick the newest file in the generated-images folder. Parallel sessions write into the same place, so the newest file can belong to another run and the wrong image gets normalized.
3. If the run output names no readable image path, treat the attempt as an empty run (see Retry and attempt limits). Do not fall back to the newest file or to a directory listing.
4. Copy the chosen image to scratch (see Sandbox (d)) and pass that copy to content icon normalize --in PATH, not the generated_images path. In the `PROMPTS.md` provenance block, record the Codex session id and only the image file name, or the path written relative to `$CODEX_HOME` (for example `$CODEX_HOME/generated_images/<file>`), in the prose beside the record. Never record the absolute path: it contains the local user name. The Provenance record fenced template itself does not change.
5. Each invocation asks for ONE image and fills ONE slot, but its output may report more than one path (for example an unreadable sandbox copy and a readable `generated_images` file). Use only paths reported by that same invocation, never a directory listing or the newest file. Select the first readable path in the order the run reported them: that single path is the candidate for the slot (one accepted candidate per slot, even when several paths are reported), and the remaining reported paths are ignored. A run that reports no readable path is an empty run: either it reports no path, or every reported path is unreadable (unreadable-only output). An unreadable path fills no slot and does not stop the run from using another readable path it reported. Parallel sessions write into the same place, so do not run candidates for several repositories in the same working directory at once unless you can tell their outputs apart.

### Retry and attempt limits

- The limit applies per candidate slot. Pipeline rule 7 asks for four single-image invocations (the option A template asks for one image each), so there are four candidate slots and the cap applies to each slot. The first readable path an invocation reports fills the slot that invocation was for; an empty run (no reported path is readable) is retried as a NEW run with the same unchanged prompt, at most 2 retries (3 attempts total) for that slot. Retries never alter the prompt. Each slot is an independent invocation, so one slot's empty run does not count against another slot.
- Successful candidates never count toward the cap, so the four-invocation round of pipeline rule 7 (then four more once, then log `art-fail`) is still reachable. Only empty runs count toward the 3 attempts, and they are not candidates. An unreadable path is not a successful candidate, so unreadable-only output is counted as an empty run and cannot loop forever. A run that reports one unreadable path and one readable path is NOT unreadable-only: it fills the slot with the readable path and is not an empty run.
- The second round of rule 7 (four more single-image invocations once) opens four new slots with the same per-slot cap of 3 attempts (2 retries each); slots from the first round do not carry over their attempt counts.
- After 3 empty attempts for any one slot, including attempts that returned only unreadable paths, stop and log `art-fail` with a one-line reason. Do not loop.

### Privacy: only public facts go into prompts

- (a) Prompts may contain only public facts: the public repository name, its public description and topics, the family palette and style lock, and the glyph fields supplied by the writer.
- (b) Never paste private-repository content into a prompt: no private repo names, README or source text, issue text, customer or personal data, emails, tokens, or estate-registry rows.
- (c) `content icon prompt` does not establish whether a fact is public. It writes repository metadata (name, description, topics) and fields derived from the local README, such as its heading, into the Markdown file that Codex receives, with no privacy filtering. Before running Codex, read the complete generated Markdown, including every README-derived field, and remove or replace anything that is not public. Use public-only inputs, or hold the task. The prompt leaves the machine.
- (d) For a private repository, do not generate the icon with Codex from its contents. Use only the family glyph fields and a neutral name, or hold the task.
- (e) Keep the prompt text in the provenance record verbatim, which makes this rule auditable.

### Sandbox: read from the generated-images folder

These are OBSERVED runtime notes from issue #64 and the Pick Your AI evidence, not behaviour documented by OpenAI. Do not cite OpenAI documentation for them; the rule that holds regardless is: use the exact path returned by the run output.

- (a) Observed: Codex stored generated images in its `generated_images` folder inside `$CODEX_HOME` (default: the `.codex` folder in the user's home, `~`). Read the image from the path named in the run output, which points there.
- (b) Observed: files that Codex writes into its own sandbox, for example a copy it saves into the working directory it was given, can be locked against the user account (access denied). Do not rely on them, and do not try to chmod or take ownership of them.
- (c) If a path is unreadable, copy nothing from the sandbox and do not retry the same path. Skip it and use the first other readable path the same run reported, if there is one. Only when no reported path is readable does the run return nothing: it is then an empty run and counts as one attempt under the retry limit above, ending in `art-fail` after 3 empty attempts for the slot.
- (d) Copy the chosen image to a scratch location outside the repository before `content icon normalize --in`, and commit only the normalized `assets/icon.png`. Never commit the raw candidate. Do not write any real absolute local path or user name; use `$CODEX_HOME` and `~` only.

## Repository glyph prompt template

`content icon prompt` uses this self-contained option A template by default. Its
palette slots and flat render inks come from the selected family's `icon_ink`
and `icon_spark` tokens in `brand.yaml`. Both are chosen to meet the icon QA's
3:1 contrast threshold on that family's card, with a distinct outline and spark.
The writer supplies the four glyph fields with `--glyph`. `size_class` accepts
WIDE (the glyph spans close to the full 688 px width and is about 430 to 560 px tall),
TALL (it spans close to the full 688 px height and is about 400 to 600 px wide),
SQUARE (a squarish glyph about 600 to 660 px on each side) and DIAGONAL (the mass runs
corner to corner inside a 656 × 656 px box). The prompt asks for one image and asserts
no seed; pass `--seed N` to request one, which the prompt and its provenance block then
record (otherwise the seed is recorded as "not supported"). It does
not require the estate's avatar tables or reference images. An explicit
`--art-direction FILE` may instead supply the estate-format `(b) Family palette`
and `(d) Shared prompt template` sections.

```text
NEON NIGHT REPO ICON · {ACCOUNT}

Create one square 1024 × 1024 px image of a single repository glyph.
Use a simple geometric silhouette with a luminous outline and one accent spark.
Keep the background empty and the glyph inside the central 688 × 688 px square.
Size class {SIZE_CLASS}.

GLYPH: {GLYPH_NAME}. {GLYPH_DESCRIPTION}
SPARK PLACEMENT: {SPARK_PLACEMENT}
PALETTE: outline {LINE_HEX}, glow {GLOW_HEX}; one spark in {SPARK_HEX}.
The spark is the only filled shape and the only element in {SPARK_HEX}; keep the
glyph outline in {LINE_HEX} so the spark remains distinct at small sizes.

No text, letters, numbers, words, logos, brand marks, human figures or third-party IP.
{EXTRA_NEGATIVES}
Produce one image.{SEED_INSTRUCTION}
The lock pass renders assets/icon.png as a flat glyph in the family's light-surface
inks, without a tile or glow. Do not render the repository name in the image.
```

## Prompt template for illustrations

```text
[STYLE LOCK — FAMILY]
FAMILY STYLE LOCK, VERBATIM

[SUBJECT]
One sentence: the single hero object or scene that represents the repository or org's function.

[OBJECTS]
3–5 objects. CompleteTech: only from the object library. T2: only objects named in the family motif.

[COMPOSITION]
Isolated platform and objects on a perfectly flat, untextured BG background; no floor, grid, gradient or glow touching the edges; 10% empty margin on all sides. Square 1024x1024 | Wide 1536x1024.

[PALETTE]
Use only these colors: PALETTE. HIGHLIGHT LINE

[EXCLUSIONS]
No text, letters, numbers, symbols, words, labels, signatures, watermarks, logos, brand marks or interface text; every paper, screen and sign surface stays blank. No people, human faces or human hands. No photorealism, no clutter, no extra objects. FAMILY ADDITIONS
```

- BG: the family background (CompleteTech `#0F172A`; jevplay-games `#F386A1`, never the halftone).
- CompleteTech palette: `#0F172A, #001F3F, #00A7FD, #0081ED, #005ADD, #FFC300, #F8FAFC, #F1F5F9, #64748B`; highlight line `Gold #FFC300 is for small details only.` Security adds `#E11D48` with `Rose #E11D48 appears on the single finding object only.`
- Family additions: Security `No skulls, hackers or padlocks with keyholes. No vendor logos or recognizable product designs.` TCG `No Pokémon creatures, Poké Balls or real card designs.` Discord orgs `No Discord logo, mascot or blurple.` jevplay-games `No branded board-game designs or trademarked packaging.` TouchedByAnAgent `One stylized robotic hand is allowed; no skin tones or body parts; nothing suggestive.`
- Repository icons (decision 12) use the same template at Square 1024x1024 with BG set to the light card colour `#F8FAFC`, because the icon sits on the light card in both the banner and the repo card. The committed `assets/icon.png` is keyed to transparency the standard way (ΔE ≤ 6, 2 px feather, trimmed to the alpha bounding box).
- Repository icon ground (option A): the prompt states the family card colour (`card_fill`, e.g. `#F8FAFC` for CompleteTech) as one perfectly flat background with no vignette, texture, gradient, shadow or glow; `content icon normalize` keys a flat ground out whatever the card colour. With `--ground auto` only a dark ground (relative luminance < 0.2) that is not within dE 12 of the card colour is kept as a full-bleed night tile; every other uniform ground (pale or card-coloured) becomes transparent. If keeping a night tile would exceed the 300 KB budget (a noisy generator ground), auto keys it to transparent instead (`auto_reason` budget-fallback). The flat-ground wording is added for both the bundled template and an estate-format `(d) Shared prompt template` (its soft light pool and its numbered BACKGROUND paragraph, including any explicit colour or radial-gradient wording, are replaced by the flat ground). The four corners count as one ground when closer than `--ground-tolerance` dE (a finite number >= 0; identical corners always count as one ground at 0) (default 3.0; pass e.g. `--ground-tolerance 5` for corner dE 3.1-4.9 from a slight vignette); above it auto fails with `icon-ground` and the message names the measured dE and the flag. `--ground keep|transparent` are unchanged (see references/content.md).
- Placing an illustration on a social preview (1280×640) or an org banner (1600×400): key out the generated background colour the same way, then scale to fit the fixed box (social preview (672, 64)–(1216, 544), centred; org banner (640, 32)–(1536, 368), right-aligned and vertically centred).

| Family | Style lock (verbatim) |
|---|---|
| CompleteTech | Clean glossy isometric 3D product illustration, orthographic isometric camera from the front-left. Every scene sits on one rounded-rectangle platform: deep navy (#001F3F) top, ink (#0F172A) sides, a thin glowing sky-blue (#00A7FD) edge line, floating above an empty background with a soft contact shadow. Objects are smooth satin plastic in sky blue (#00A7FD), azure (#0081ED), royal blue (#005ADD) and off-white (#F1F5F9), with small warm-gold (#FFC300) details. Glass parts are frosted translucent blue. Thin gold circuit traces ending in round solder pads link the objects across the platform top. Soft rounded geometry, subtle bevels, bloom on gold details only, key light from the upper left, calm and uncluttered. |
| jevplay-games | Bold retro pixel-art illustration with chunky one-pixel dark outlines at a clearly visible pixel scale, flat colors on a plain flat pink background, and a playful early-desktop-computer aesthetic with simple window frames. |
| Jev-Engineering | Minimal glowing vector-style 3D render on a near-black background: smooth neon lines and nodes, soft cyan and violet glow, clean geometric primitives, calm technical mood, no clutter. |
| LibreEvolve | Minimal glowing illustration on dark navy: a luminous emerald branching structure, soft depth of field, most branches dim and fading, one path bright, calm scientific mood. |
| TouchedByAnAgent | Glossy 3D product illustration on deep maroon: smooth pink-peach robotics, warm amber glow, soft magenta signal ripples, tasteful and non-suggestive, studio lighting. |
| romgenie | Glossy illustrated 3D still life in a warm vault: brass-bound objects, soft lamp light from above, dark teal ambient background, storybook-premium finish. |

## Provenance record (`PROMPTS.md`, one block per committed asset)

```markdown
## assets/icon.png
- Date: YYYY-MM-DD
- Tool and model: TOOL / MODEL ID AND VERSION
- Seed: SEED or "not supported"
- Reference images: golden reference path, jev-reference.png, or "none"
- Prompt: (verbatim, fenced)
- Images requested: as asked in the prompt (`content icon prompt` asks for 1); selected: N (reason: one line)
- Post-processing: showcase.py VERSION; output sha256 HASH; size KB
```

## Art QA checklist (all MUST pass before commit; also the candidate rejection rules)

- Exact pixel dimensions and size limits (the two logo hashes are exempt).
- No glyph-like marks: zoom to 200% on every surface.
- No human figure (TouchedByAnAgent: one stylized robotic hand only).
- No object inside the 10% margin of the generated image.
- Palette: quantize to 8 colours; every cluster covering at least 5% of pixels is within ΔE2000 ≤ 12 of a family palette colour.
- Typeset text contrast at least 4.5:1 against the canvas under it.
- No third-party marks.
- The avatar reads at 20 and 40 px; the card reads at 400 px wide; the banner reads at 1012 px and 390 px wide.
- The banner is opaque, so it works on GitHub light and dark themes.
- Alt text describes the art literally.
- Judged as a set (decision 10): every org's banners, cards and icons on one contact sheet, on both page colours.
