# ClawHub Publishing

This repository is prepared for ClawHub publishing as a text-based OpenClaw skill bundle.

## Included In ClawHub

The ClawHub bundle is intended to include text-based skill material only:

- `SKILL.md`, `README.md`, `QUALITY.md`, and this file
- `agents/openai.yaml`
- `action.yml`
- `pyproject.toml` and `requirements.txt`
- `.github/workflows/*.yml`
- `scripts/*.py`, `scripts/ctshowcase/*.py` and `scripts/action_commit.sh`, except the development-only `scripts/validate_quality.py`
- `references/` text files, YAML data, schemas and the standard excerpts
- `assets/fonts/FONTS.json` and the `*-OFL.txt` license texts
- `assets/diagrams/*.mmd`
- `examples/` text inputs: synthetic metadata JSON and the example `showcase.yml`
- generated SVG examples (`assets/examples/*.svg`, `docs/images/card.svg`), which are text

## Excluded From ClawHub

`.clawhubignore` excludes binary and generated assets from the publish candidate, including PNG banners and previews, WebP files, fonts (`*.ttf`), logos and brand masters, `preview/`, `output/`, the `.showcase-cache/` render cache, caches, virtual environments, local env files, and temporary files.

Those files remain part of the GitHub repository for brand presentation, examples, local demos, and generated artifact previews. They are not part of the ClawHub text bundle.

What the text bundle can do on its own:

| Works directly from the text bundle | Needs the binary files first |
|---|---|
| `describe`, `topics`, `labels`, `lint`, `readme`, `doctor`, `footer`, `meta`, `fingerprint` | `banner`, `card`, `org-tile`, `intro` and `contact-sheet` |

For the generators, run `python3 scripts/showcase.py fonts --fetch` once. It downloads the pinned OFL fonts from their upstream releases and verifies each against the sha256 in `assets/fonts/FONTS.json`. Then pass the logo or icon with `--icon`, or point `brand_assets` in a local copy of `references/brand.yaml` (via `--config`) at your own copies of the CompleteTech brand files. The bundle never downloads logos.

## License And Brand Boundary

ClawHub publishes skills under MIT-0. The text/code bundle can be used under ClawHub's publishing terms, but CompleteTech LLC names, logos, seals, and other brand assets remain reserved. Publishing this text bundle does not grant a trademark or brand-asset license and does not relicense excluded binary brand assets. The bundled fonts keep their SIL Open Font License; their license texts travel with the bundle.

## Runtime Dependencies

Runtime requirements are declared in `SKILL.md` under `metadata.openclaw`, pinned exactly as in `requirements.txt`.

- `python3` is required for every command.
- `fonttools==4.67.0` and `uharfbuzz==0.57.0` shape and outline text for every generator.
- `pillow==13.0.0` composites the PNG banner, PNG previews and contact sheets, and encodes embedded WebP icons.
- `pyyaml==6.0.3` reads `brand.yaml`, `labels.yml`, workflows and frontmatter.
- `gh` (GitHub CLI) is optional; only `meta --from-gh` and `labels --plan` without a metadata file use it, for read-only GETs.
- `meta` and `fingerprint` use the standard library only, so the composite Action can decide whether anything changed before installing packages.

## Local Readiness Check

Run before publishing:

```bash
python3 scripts/validate_quality.py
```

The validator checks lint, Python compilation, structured-file parsing, Mermaid rendering, smoke tests, Pyright where configured, the showcase gates in `QUALITY.md`, and ClawHub bundle readiness. It does not publish to ClawHub.

## Publishing

Do not publish automatically. Use the ClawHub CLI only after explicit approval and an authenticated owner context, for example:

```bash
clawhub skill publish . --owner <owner> --version <semver>
```
