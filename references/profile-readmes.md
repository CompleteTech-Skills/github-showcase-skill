# Profile READMEs

Condensed from the estate's profile README kit (decision 15), with decision 21 applied: every generated image is one dark file used on both GitHub themes. It covers the CompleteDotTech personal profile (`CompleteDotTech/CompleteDotTech`), every org's `.github/profile/README.md`, and the romgenie profiles. The goal is a polished, business-grade set of profiles that look related, not a collection of widgets.

## Rules

1. **Nothing the page depends on comes from a free third-party server.** Hosted stats cards get rate-limited and break on every profile at once. A scheduled Action in the profile repository generates dynamic content, commits the SVG or Markdown, and the README references only its own files.
2. **One dark design, literal alt text.** Intro, cards, tiles and plates are single dark files embedded with a plain `<img>`; the navy plate reads on both page colours. The decision 18 footer logo is the only `<picture>`.
3. **Same structure everywhere.** Every org profile follows the same section order; only content and the family palette change.
4. **Truthful numbers or none.** Most work is in orgs and private repositories, so personal stats cards undercount. Prefer projects, releases and cross-listings. Counts that change live in Markdown, never inside an image.

## Use

| Need | Approach |
|---|---|
| Badges | One style estate-wide (brand-family colours, Simple Icons slugs), rendered offline and committed (`--badges local`); never hotlinked from a badge server on profiles |
| Hero | The profile intro (`showcase.py intro`) on the personal profile and T1 flagship orgs; the org banner elsewhere |
| Latest activity across the estate | Own scheduled Action that rebuilds the README from the registry (recent releases and recently updated repositories across in-scope orgs) |
| Featured repositories, cross-listings | Repo cards (`showcase.py card`), generated from the registry and committed |
| Org directory | Org tiles (`showcase.py org-tile`) for flagships and family heads, plus a text index in `<details>` |
| Blog or RSS posts | Only if complete.tech has a feed |
| Tech stack | One static stack plate: 2 rows of 6 vendored single-colour icons at 48 px with labels, from the languages the estate actually uses |

**Skip:** visitor counters, jokes, memes, quotes, now-playing cards, anime or zodiac cards, contribution snakes, pets and similar novelty animations, trophies, developer-rank cards, WakaTime cards, hotlinked `github-readme-stats` or similar images, mixed icon sizes, and multi-megabyte GIFs.

## Org profile section order

1. Banner (the org name is inside the banner art, so no separate H1).
2. One-sentence mission (the first sentence of the org description, verbatim) and 3–5 badges (website, contact, family link back to complete.tech).
3. **Featured**: the org's public pins as repo cards, matching the pin row above.
4. **All projects**: a generated Markdown table grouped by type (clickable, searchable, readable on a phone); never images.
5. **Also from CompleteTech**: repositories homed elsewhere that list this org in `also_in`, plus sibling orgs in the same family.
6. **Favorites**: outside projects this org builds on, with a link to the matching star List if one exists.
7. Footer: contributing, security and contact links, and the CompleteTech LLC footer.

Public org text never names a private repository, client, person, codename or strategy. Private repositories are never listed. An org with no public repositories shows the banner, the mission, the line `Work in this organization is private. Public CompleteTech projects are listed at [github.com/CompleteTech-LLC](https://github.com/CompleteTech-LLC).`, then the footer.

## Personal profile section order (CompleteDotTech, built last)

`showcase.py org profile --user CompleteDotTech --meta-dir DIR [--out-dir CHECKOUT --render]` renders it from the registry's top-level `profile` (public slice: public, non-fork, non-archived pins and more projects only; no placeholder org, no T3 org before sign-off; no `why` or `notes` text) and runs the `lint public-leak` check against the whole estate before it writes `README.md` and `data.json` (and, with `--render`, the badges, cards and org tiles). The intro is the `intro --profile CompleteDotTech` asset it lists. The tech stack is a Markdown share line computed from the public repositories' `languages` until the stack plate exists.

1. Animated intro (`assets/intro.svg`, one file).
2. Social badge row (at most 5: website, X, LinkedIn, email), from the registry.
3. Who and what in two sentences: Timothy Wayne Gregg, CompleteTech LLC, Cincinnati, "Innovation at Every Integration", with a `<sub>` facts line.
4. Flagship repo cards, matching the 6 profile pins.
5. Orgs directory: the unified avatar set as a grid, each linking to its org; flagships and family heads as org tiles.
6. Tech-stack plate.
7. `<details>`: more projects (extra cards).
8. `<details>`: latest activity across the estate (generated).
9. Contact, as real Markdown links.

`<details>` sections stay closed by default, leave a blank line after `<summary>`, and put any count in `<sub>`.

## Surfaces

| Surface | Spec |
|---|---|
| Personal intro | 1280×320 navy grid plate; mark on the left with a radial glow; eyebrow `COMPLETETECH LLC · CINCINNATI, OHIO`; `Timothy Wayne Gregg` in Poppins SemiBold 62 px; typed tagline `Innovation at Every Integration` in JetBrains Mono 32 px with a caret that blinks 3 times then stays solid; chips gold `complete.tech`, blue `Founder` and `AI integration`; gold circuit traces drawn in from pads outside the mark, three signals on 6.1, 7.7 and 9.3 s loops; a `.still` reduced-motion frame. See [banner-layout.md](banner-layout.md). |
| T1 flagship org intro | The same template with the org display name and `COMPLETETECH LLC · ORG EYEBROW`; traces end beside the org's card illustration. Only these orgs and the personal profile animate. |
| Repo card | 400×160, two per row at `width="400"`; the same component for Featured, extra pins and cross-listings. See [banner-layout.md](banner-layout.md). |
| Org tile | 400×160 org variant of the card: avatar, display name, family eyebrow, optional illustration on the right. |
| Divider | One 1200×20 static divider per family above real Markdown H2s; headings are never images. |
| Stack plate | One static image, 2 rows of 6 icons, JetBrains Mono labels, share bars from the audit's language bytes. |

## Family skins

All families use the same plate and pieces with different skins:

| Family | Skin |
|---|---|
| CompleteTech core | Navy grid; gold solder-pad rings; the royal bar ending in a gold pad as the divider; the final animated frame equals the static plate |
| Jev Engineering | Near-black, no grid; one hub fanning on curved lines into lanes ending in a circle, square, triangle and diamond |
| jevplay.games | Unrotated halftone, crisp edges, no grain; pixel-stepped retro windows; Jev only from `jev-reference.png` with nearest-neighbour integer scaling; Press Start 2P at 36 px or larger |
| LibreEvolve | A lineage tree generated offline (seed 4001): faded branches, one bright path running off the edge |
| romgenie archive and following | A brass double hairline with corner brackets on flat dark teal, shared by both orgs |
| Touched By An Agent | Faint amber and magenta ripple arcs; on hold until the user decides |
| AI Ascension | Keeps its existing banners; shared pieces get an amber hairline, outlined Fraunces titles and a mono eyebrow |
| T3 | Untouched until co-owner sign-off |

## Not used, and why

Novelty contribution games, hotlinked stats and typing services (they break rule 1), filter-heavy animated looks (62–90% main-thread cost), jitter or flashing animation, imitation trading cards, more than one perpetual motion per page, anything clickable that exists only inside an image, web-font-first font stacks, symbol glyphs, `feTurbulence` grain, and 9–11 px tracked labels that carry information.
