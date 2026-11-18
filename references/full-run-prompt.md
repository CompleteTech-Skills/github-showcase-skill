# Full-capacity run prompt

A copy-ready prompt that has an agent (Claude Code or Codex, with this skill installed) run the whole pipeline on
one target: a repository, an organization, the personal profile or the Enterprise. Repository icons and org
illustrations come from an image model through the
[Codex image-generation recipe](art-direction.md#codex-image-generation-recipe). Every word, mark, banner, card,
tile, intro and profile is still rendered by `scripts/showcase.py`, and every GitHub change leaves as a writer
job or `gh` line for approval. Nothing in the prompt writes to GitHub.

## How to use it

1. Copy the prompt below with the code block's copy button.
2. Replace `<SKILL_DIR>` with this skill's checkout and `<PY>` with its virtual environment's Python
   (`.venv/bin/python`, or `.venv\Scripts\python.exe` on Windows).
3. Adjust the run options if needed, and replace the last line with the target: `OWNER/REPO`, an org login,
   `CompleteDotTech` or `enterprise:SLUG`.
4. Send it to the agent. It stops only to ask for the flags or approvals the skill requires (STOP 1) and for
   the per-family pilot approval (STOP 2).

`SKILL.md` and the references stay authoritative: when they change, they win over the prompt, and the agent
names the conflict in its report.

````markdown
# GitHub Showcase: full-capacity run

You are running the CompleteTech `github-showcase-skill` (checkout at `<SKILL_DIR>`) end to end on the TARGET
named on the last line. Produce every applicable surface: repository icons drawn by an image model, then the
skill's deterministic banner, card, social preview, README, org banner, tile, intro and profile. Run every audit,
emit every GitHub change as a reviewable plan, and prove the result on contact sheets. Work autonomously and
stop only at STOP 1 and STOP 2.

Before acting, read `SKILL.md`, `references/art-direction.md`, `references/content.md` and
`references/decisions.md`; for org, project or enterprise targets also `references/org.md`,
`references/projects.md` and `references/enterprise.md`. Where they disagree with this prompt they win; name
the conflict in the report.

## Hard rules
1. Every generation, check and plan runs through `S="<PY> <SKILL_DIR>/scripts/showcase.py"`, from inside the
   target checkout. Put `--format json` before the command when you parse a generator's result. Never
   hand-edit a generated file, marker block or profile README: fix the input (`.github/showcase.yml`, the
   description, a flag) and regenerate.
2. Nothing is written to GitHub: no `gh` write verbs, no push, no commit, no settings. Proposals leave as
   `--jobs $WS/jobs.jsonl`, `--records $WS/records.jsonl`, `--gh` lines and diffs. Local outputs stay
   uncommitted in each checkout for review. Clones and read-only `gh api` GETs are fine.
3. Gates are answers. Never pass `--allow-hold`, `--allow-unmeasured` or `--allow-t3` on your own, never use
   `--allow-few-chips`, and skip excluded owners. Exit 3 and 4 name the input to fix (Appendix A).
4. The image model draws illustration layers only: no text, letters, numbers, logos, marks, people or
   third-party IP. Marks come only from committed files, and the skill typesets every word.
5. Only public facts leave the machine. Read every prompt in full before sending it. For a private repository,
   send only the glyph fields with a neutral name in place of the slug, or hold it.
6. One dark design per surface (decision 21): never a light variant or a `-dark`/`-light` sibling.
7. Keep `$WS/ledger.jsonl`, one line per finished step (target, step, outputs, sha256, result), so an
   interrupted run resumes without regenerating paid art.

## 0. Resolve the target
- `OWNER/REPO` is a repository. `enterprise:SLUG` is the enterprise (`enterprise:?` runs `$S enterprise
  discover` first). A bare login: `gh api users/LOGIN --jq .type` gives `Organization` (org run) or `User`.
- The only supported personal account is `CompleteDotTech` (`org profile --user` refuses every other); stop
  for any other user.
- Resolve org logins through the skill (former logins resolve, CQ-03) and report any rename found.

## 1. Preflight
- `WS` = a new scratch directory outside every repository, holding `meta/`, `checkouts/`, `tools/`,
  `art/{prompts,runs,candidates,golden}/`, `proof/`, `jobs.jsonl`, `records.jsonl` and `ledger.jsonl`.
- Create a venv, `pip install -r <SKILL_DIR>/requirements.txt`, then `$S fonts --check` (`--fetch` on failure)
  and `$S config`.
- Tools: `gh auth status`; `codex --version` and `codex exec --help` (this run uses `--json`,
  `--skip-git-repo-check`, `-C`, `-i`, `-m` and `-` for stdin; if a flag is rejected, adapt only that flag);
  `tesseract` enables `--ocr` (absent is fine, logged `needs-input:ocr-unavailable`).
- Estate bundle: if one is present (`SHOWCASE_ESTATE_ROOT` or beside the skill) read it, never copy it.
  Without it, use the registry-free paths named below.

## 2. Scope (STOP 1 only if something needs me)
- Repositories: one for a repo target; for an org, the registry or
  `gh repo list ORG --limit 1000 --json name,visibility,isFork,isArchived`.
- For each: `gh repo clone OWNER/REPO $WS/checkouts/OWNER/REPO -- --depth 1` (also clone `OWNER/.github` when
  it exists), then `$S meta --from-gh OWNER/REPO --out $WS/meta/OWNER/REPO.json`.
- Classify the results:
  - A refusal or exemption (exit 2: `exempt`, `hold`, `t3-signoff`) is skipped and logged.
  - `needs-input:palette-v1.1` (an unmeasured family), a family on hold, a T3 owner, or an org with no
    `brand.yaml` row (show the `brand add-org` dry run) goes on the STOP 1 list.
  - A low-confidence `type-suggestion` is decided from the file tree and set as `type:` in
    `.github/showcase.yml`.
- STOP 1: show the scope table and the flags or approvals it needs. If nothing needs me, continue.

## 3. Facts before art (per repository; `cd` into its checkout; `M=$WS/meta/OWNER/REPO.json`)
1. `$S --meta $M describe`. On `needs-writer`, write the sentence from `references/descriptions.md` and the
   repo's facts, and iterate `describe --text "..."` until it answers `keep`. Also run
   `lint prose --prose-kind description --text "..."`. If the result differs from the live description, it is
   STAGED.
2. `topics --gh --records $WS/records.jsonl` (add `--registry` when the bundle exists).
3. `labels --plan --org-defaults $WS/checkouts/OWNER/.github --jobs $WS/jobs.jsonl --records $WS/records.jsonl`.
4. Every later generator for this repository gets `--description "$STAGED"`, so R2 still holds once the
   writer applies the description.

## 4. Art from the image model
### 4a. Repository icon (decision 12): before the banner, card and social preview, which embed it
1. Skip it if `assets/icon.png` exists and `content icon check` passes.
2. Write `$WS/art/prompts/OWNER/REPO/glyph.yaml`.
   - Option A: `glyph_name`, `glyph_description`, `spark_placement`, and `size_class`
     (WIDE|TALL|SQUARE|DIAGONAL). The description is one simple geometric silhouette of what the repository
     does, distinct at 48 px from the org glyph and from its siblings' icons.
   - Option B: `subject` and `objects` (3–5 from the object library or the family motif).
3. Run `$S --meta $M content icon prompt --option $ICON_OPTION --glyph glyph.yaml --out .../icon.md` until it
   answers `result: ok`.
4. Copy only the fenced `text` block of `icon.md` into `prompt.txt`. The rest of the file is notes for you,
   including a "Then: run normalize" line the image agent must not act on. Apply rule 5.
5. Run four candidate slots serially. Each is one image in its own new, empty directory `$SLOT`:
   `codex exec --json --skip-git-repo-check -C "$SLOT" [-m $IMAGE_MODEL] [-i REF.png ...] - < prompt.txt > "$SLOT/run.jsonl"`
   - The candidate is the first readable image path this run's own output reports. Never use the newest
     file in `generated_images` or a directory listing. Copy it to
     `$WS/art/candidates/OWNER/REPO/slot-N.png`.
   - A run with no readable path is empty. Retry that slot with the unchanged prompt, at most 3 attempts,
     then `art-fail` for the slot.
   - `-i` references must be text-free: this family's approved golden icons (after STOP 2), and
     `jevplay-games/.github/profile/assets/jev-reference.png` for every jevplay-games prompt. Never attach
     a banner or card; they contain text.
   - Use one tool and model per family. Request a seed only through `content icon prompt --seed N`.
   - `IMAGE_TOOL: api`: any image API you are configured for, with `prompt.txt` verbatim, one 1024×1024
     image per call. Record the model id the response reports, or `not exposed`; never invent one.
6. Inspect each candidate at 200% before normalizing it. Reject any with glyph-like marks, people, objects
   inside the 10% margin, a non-flat ground or off-palette colour.
   - Take the survivors in generation order: `content icon normalize --in slot-N.png --ground auto --preview
     $WS/proof/OWNER__REPO-icon-48.png [--ocr]`, then `content icon check --strict --min-contrast 4.5`. The
     first that passes wins; record a one-line reason.
   - For a slight vignette (corner dE 3–5), add `--ground-tolerance 5`. Never lower the QA bar.
   - If none of the four passes, run four more slots once, then log `art-fail`. The banner falls back to
     the org mark (`needs-input:repo-icon`).
7. Append the provenance block to `assets/PROMPTS.md` in the format in art-direction.md:
   - date, tool and model as reported, seed, reference images;
   - the prompt verbatim, images requested and selected, the reason;
   - showcase.py version, sha256 and size.
   Record the Codex session id and the image name relative to `$CODEX_HOME`; never an absolute path or user
   name. Raw candidates never enter a repository.

### 4b. Org illustration (org targets)
1. Fill the art-direction "Prompt template for illustrations":
   - the family STYLE LOCK, verbatim;
   - SUBJECT: one sentence for the org's function;
   - OBJECTS: the org's motif row (CompleteTech) or the family motif (T2);
   - Wide 1536x1024 on a perfectly flat family canvas (CompleteTech `#0F172A`; jevplay-games `#F386A1`,
     never the halftone);
   - the PALETTE and highlight line, the EXCLUSIONS and the family addition.
   Save it as `$WS/art/prompts/ORG/org-banner.md`.
2. Generate and select it with steps 4a.5–6 (visual QA only; `icon normalize` does not apply).
3. Key it with `<PY> $WS/tools/key_illustration.py slot-N.png $WS/art/ORG-illustration.png <CANVAS_HEX>`
   (Appendix B). The generators place an illustration as-is, so an unkeyed ground shows as a dark rectangle
   over the grid.
4. Record its provenance in `.github/profile/assets/PROMPTS.md`.

### 4c. Pilot gate (STOP 2)
When more repositories of the same family remain in this run, render the first one completely (icon, banner,
card, social preview, plus the org banner for an org run). Put it on a contact sheet, show me both page
colours and wait for approval, unless PILOT_APPROVED is yes. Copy approved text-free art to
`$WS/art/golden/<family>/` and attach it as `-i` references for the rest of that family.

## 5. Deterministic surfaces (per repository, in this order)
1. `banner` writes `docs/images/banner.png`.
   - `needs-input:banner-chips`, `key-chip` or `subtitle`: add `chips:` or `subtitle:` from real facts to
     `.github/showcase.yml`.
   - `art-fail`: shorten the subtitle; never truncate.
2. `card --png $WS/proof/OWNER__REPO-card.png` writes `docs/images/card.svg`. `exempt:no-card` for forks,
   backups and `.github` is correct.
3. `content social --job --jobs $WS/jobs.jsonl` writes `assets/social-preview.png` and its browser upload
   job.
4. `readme --diff`: save the diff to `$WS/proof/OWNER__REPO-readme.diff`, then run `readme --write`. On
   `readme-shrink`, stop this repository and report it.
5. `footer --check README.md --online`.

## 6. Content audits (per repository; proposals only)
- `content links --base-ref origin/<default_branch> --online --cache $WS/links-cache.json --diff`
- `content linguist`
- `content images --out-dir $WS/proof/OWNER__REPO-images`
- `content actions --runs runs.json --workflows workflows.json [--pages pages.json]`, captured with
  `gh api repos/O/R/actions/runs?per_page=50`, `gh api repos/O/R/actions/workflows` and
  `gh api repos/O/R/pages` (omit `--pages` on a 404).
- `content sidebar --facts $M`
- `adopt OWNER/REPO --jobs $WS/jobs.jsonl --records $WS/records.jsonl` when the repository had no
  `docs/images/.showcase.json` before this run.

## 7. Scope extensions
### Organization (after its repositories)
- `org about ORG --jobs $WS/jobs.jsonl`
- `org labels ORG --meta-dir $WS/meta/ORG --checkouts $WS/checkouts --dot-github $WS/checkouts/ORG/.github
  --jobs $WS/jobs.jsonl`. Without the registry, use `--repos-from-gh` instead of `--meta-dir` and no
  registry inputs.
- `org profile ORG --meta-dir $WS/meta/ORG --out-dir $WS/checkouts/ORG/.github --render`, then
  `org-banner --org ORG --illustration $WS/art/ORG-illustration.png
  --out $WS/checkouts/ORG/.github/profile/assets/banner.jpg`. This replaces the plain banner the profile
  render wrote and clears `needs-input:org-illustration`.
- `org-tile --org ORG --illustration $WS/art/ORG-illustration.png --out $WS/proof/ORG-tile.svg
  --png $WS/proof/ORG-tile.png`. On `art-fail:tile-name`, rerun without `--illustration`; the illustration
  only fits short names.
- For a T1 flagship org: `intro --org ORG --out $WS/checkouts/ORG/.github/profile/assets/intro.svg`. Use it
  as the profile hero (`org profile --banner assets/intro.svg`) only where `references/profile-readmes.md`
  says so.
- `lint public-leak` on every public file written (`--meta-dir $WS/meta/ORG`; registry-free:
  `--denylist $WS/private-names.txt`, one private repository name per line).
- `org pins ORG --jobs $WS/jobs.jsonl` and `org health ORG --dot-github $WS/checkouts/ORG/.github`.
- Run `org doctor ORG --doctor-format json` once. Run the read-only `reads` argv it lists, assemble the
  snapshot `{org, graphql, repos, profile_readme}` per `references/org.md`, then run
  `org doctor ORG --snapshot $WS/ORG-snapshot.json --dot-github $WS/checkouts/ORG/.github
  --avatar <current avatar PNG> --doctor-format md --header`. Avatars are checked, not generated.
- Project board: find N with `gh project list --owner ORG --format json`, then
  `project capture-query --owner ORG --number N`. Run the printed query with `gh api graphql`, then
  `project normalize` and `project lint --capture F --owner ORG --role org`. If the board is missing or fails,
  run `project copy-plan --target ORG --jobs $WS/jobs.jsonl` (stage 1). Stage 2 (`--copied`) waits for the
  writer, so list it as pending.
- With the registry: `doctor --estate --meta-dir $WS/meta/ORG --out $WS/NEW_PROPOSALS.yaml`.

### Personal account (CompleteDotTech)
- `org profile --user CompleteDotTech --meta-dir $WS/meta --out-dir $WS/checkouts/CompleteDotTech/CompleteDotTech --render`
- `intro --profile CompleteDotTech --out $WS/checkouts/CompleteDotTech/CompleteDotTech/assets/intro.svg`
- Run phases 3, 4a and 6 on the profile repository, plus `content social` and `footer --check README.md`.
  Skip `banner`, which is exempt because the profile opens with the intro, and `readme`, because
  `org profile --user` owns that README.md.
- `lint public-leak` on every public file written.

### Enterprise
- `enterprise snapshot --slug SLUG --out $WS/enterprise/snapshot.json` (read-only GraphQL;
  `enterprise snapshot-query --slug SLUG` shows the queries).
- `enterprise doctor --snapshot F [--baseline OLD]`, `enterprise seat-check --snapshot F`, and
  `enterprise plan --snapshot F --jobs $WS/jobs.jsonl --records $WS/records.jsonl`. Add
  `enterprise diff --baseline OLD --snapshot F` when a baseline exists.
- No art at this level. List the member orgs with their `org doctor` rows and recommend which to run next.
  Run them only if FAN_OUT is yes.

## 8. Verify and prove
- Per repository: `lint all`, `lint svg --kind card docs/images/card.svg`, `lint banner`, and
  `doctor --header --format md`. A repository is done only when every cell is pass, warn, incomplete or n/a.
- Set review: `contact-sheet <every banner> --mode stack --labels --out $WS/proof/banners`. For an org, also
  `contact-sheet --org ORG --cross-surface --avatar A --banner B --card C --social D --org-banner E
  --out $WS/proof/ORG-g4`.
- Open both `.on-github-dark.png` and `.on-github-light.png` yourself. Fix anything clipped, illegible or
  off-family by regenerating from inputs, then re-run the checks.

## 9. Final report
1. Scope: target type; repositories in and out, with reasons; flags used and who approved them.
2. Doctor rows (md) per repository, plus the org O-row or the enterprise E-cells.
3. Files written per checkout (path, sha256, KB), with `git status --short`. Everything is uncommitted.
4. Art provenance per asset: tool and model, slots used, the selected candidate and its reason, rejects and
   their reasons.
5. Plans: `$WS/jobs.jsonl` grouped by kind and `approval_id`, and the exact `gh` lines in apply order
   (description and topics first, because the art reads them).
6. Open items: every `needs-input:*`, `owner_pending` and held item, and every check not run, with the reason.
State plainly that nothing was written to GitHub.

## Appendix A: exit codes
| Exit | Meaning | Response |
|---|---|---|
| 0 | ok, warn, incomplete, n/a | Continue; collect the `logs`. |
| 1 | a check failed | Fix the cause in the inputs and re-run. Never edit outputs. |
| 2 | refused or usage | Fix a usage error. Skip and log a refusal (`exempt`, `hold`, `t3-signoff`). |
| 3 | `art-fail` | Shorter subtitle, other chips, the next candidate. Never truncate. |
| 4 | `needs-input:<x>` | Supply `<x>` (chips, subtitle, glyph, art direction) or record it as `owner_pending`. |

## Appendix B: `$WS/tools/key_illustration.py` (Pillow only, a declared dependency)
```python
"""Key a flat-ground illustration to transparency for `org-banner` / `org-tile --illustration`
(art-direction.md: CIE76 dE <= 6 from the ground, 2 px feather, trimmed to the alpha box). Pillow only.
Usage: python key_illustration.py IN.png OUT.png [GROUND_HEX]   (default ground: the four corners, which must agree)"""
import sys
from PIL import Image, ImageFilter


def lab(p):
    def lin(c):
        c /= 255.0
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = (lin(float(v)) for v in p[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def de(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
w, h = im.size
if len(sys.argv) > 3:
    hx = sys.argv[3].lstrip("#")
    ground = tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
else:
    corners = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    spread = max(de(lab(a), lab(b)) for a in corners for b in corners)
    if spread > 3.0:
        sys.exit(f"corners are not one flat ground (dE {spread:.2f} > 3): regenerate with a flat background")
    ground = tuple(round(sum(c[i] for c in corners) / 4) for i in range(3))
g, cache = lab(ground), {}


def key(p):
    if p not in cache:
        cache[p] = 0 if de(lab(p), g) <= 6.0 else 255
    return cache[p]


pixels = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
alpha = Image.new("L", im.size)
alpha.putdata([key(p) for p in pixels])
rgba = im.convert("RGBA")
rgba.putalpha(alpha.filter(ImageFilter.GaussianBlur(2)))
box = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
if not box:
    sys.exit("nothing left after keying")
rgba.crop(box).save(out, optimize=True)
print(f"keyed {src} -> {out} box={box} ground=#{''.join(f'{v:02X}' for v in ground)}")
```

## Run options (defaults; edit before sending)
- ICON_OPTION: A  (A = Neon Night glyph, B = isometric illustration)
- IMAGE_TOOL: codex  (codex, api, or none; none = no generated art, banners use the org mark)
- IMAGE_MODEL: default  (pin with `-m` only when you name a model; one model per family)
- PILOT_APPROVED: no  (yes = this family's golden references are already approved; skip STOP 2)
- FAN_OUT: no  (enterprise only: also run every member org)

TARGET: <OWNER/REPO | ORG | CompleteDotTech | enterprise:SLUG>
````

## Why some steps are there

- `labels --plan` takes `--org-defaults`. Without the owner's `.github` default issue forms, every label rename
  is held (`needs-input:label-references`, exit 1).
- Only the fenced `text` block of `icon.md` goes to the image tool. The file's notes include a
  "Then: run normalize" line meant for the operator, not the image agent.
- Org illustrations are keyed before use (Appendix B). `org-banner` and `org-tile` place an illustration as
  given, so an unkeyed flat ground renders as a rectangle over the grid.
- `org-tile --illustration` leaves 136 px for the org name, so typical names return `art-fail:tile-name`; the
  prompt then renders the tile without the illustration.
- The icon comes before the banner, card and social preview because all three embed `assets/icon.png`.
- The profile repository skips `banner` (exempt: it opens with the intro) and `readme` (`org profile --user`
  owns its README.md).

## Verification

Checked on 2026-11-18 against `main` at `bc4e10b`, on Windows with Python 3.14 and the pinned requirements, in a
scratch copy of the synthetic Northwind fixtures (`examples/`). These ran:

- the repository steps (`describe`, `topics`, `labels --plan`, `content icon prompt`, `normalize` and
  `check` at `--min-contrast 4.5` on a synthetic stand-in candidate, `banner`, `card`, `content social`,
  `readme`, `footer --check`, `lint all`, `doctor` and `contact-sheet`);
- the org steps (`org about`, `org profile --render`, `org-banner` with an unkeyed and a keyed stand-in
  illustration, `org-tile` with and without one, `intro`, `org doctor` and `lint public-leak`);
- `enterprise doctor` on the test snapshot.

The Appendix B keyer produced the same pixels as a numpy implementation and took 2.4 s on a worst-case
1536×1024 noise image.

Not run: a real image generation (Codex or an API), live `gh` captures (`meta --from-gh`, org snapshots,
project boards) and a fresh virtual machine.
