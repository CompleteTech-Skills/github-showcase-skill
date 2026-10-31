# Quality Checks

Run the production-readiness checks from this repository root:

```bash
python3 scripts/validate_quality.py
```

The validator compiles Python files, runs Ruff, parses YAML/JSON/INI files, renders Mermaid sources when Mermaid tooling is available, runs generator `--help` smoke checks where generator scripts exist, runs catalog `--list` smoke checks where renderer catalog scripts exist, and runs Pyright when a `pyrightconfig.json` file is present.

GitHub Actions runs the same validator on push and pull request.

## Showcase gates

This skill adds these gates to the family validator. Each one fails the run:

| # | Gate | What it proves |
|---|---|---|
| 1 | `showcase.py --help`, every subcommand `--help` and every `content` action `--help`; each command and each `org`, `project`, `enterprise` and `content` action is offered by the CLI and appears in the `SKILL.md` Command Reference | The CLI loads, keeps the command-group contract other workstreams call by name, and documents every command in `SKILL.md`. |
| 2 | `references/brand.yaml` validates against `references/brand.schema.json`; `references/brand.lock.json` is in sync | The stdlib-only commands (`meta`, `fingerprint`) read the same brand data as the generators. |
| 3 | No hex colour literal (`#RRGGBB`) in `scripts/` | Colours come only from `brand.yaml`. |
| 4 | `showcase.py fonts --check`, and an `*-OFL.txt` beside every TTF | The bundled fonts are the pinned OFL files. |
| 5 | Every `examples/meta/*.json` renders a banner, card, tile and intro into a temp directory; each lints PASS; a second render is byte-identical | Generators are correct and deterministic. |
| 6 | `labels --emit-yml` equals the `labels.yml` text of the standard | The label set has not drifted. |
| 7 | `action.yml` parses and declares the documented inputs | The template's Action contract holds. |
| 8 | Privacy: fixtures (including `examples/estate/meta`) are public or owned by `Northwind-Trading-Co`; no private owner/repo pair appears (hashed deny-list, when supplied) | No private-repo metadata ships in the package, and the real estate registry is never copied into it. |
| 9 | `lint readme README.md` and `footer --check README.md` on this repository's README | The skill passes its own standard. |
| 10 | `CHANGELOG.md` exists and has a `## <version>` (or `## [<version>]`) entry for the `SKILL.md` frontmatter `version` | Every released version is described. This check lives here, not in the shared `scripts/validate_package.py`, which stays byte-identical to the siblings'. |

Run the test suite as well:

```bash
python -m pytest -q
```

The `Test portability` workflow runs this full suite on Windows, Linux and macOS.
Only Action shell tests marked `requires_bash` may skip when a compatible shell is
absent; Windows uses Git for Windows' shell, not the WSL launcher. See the
[Windows test triage](references/windows-testing.md) for encoding and path handling.

It covers the typesetting engine, the PNG and SVG backends, banner geometry against the golden layout mask, chip rules, cards, tiles, intros, the footer, README scaffold and upgrade (including the never-delete multiset property), descriptions, topics, type detection, labels, both linters, contact sheets, `doctor`, the Action contract, the org resolver (renamed and merged org logins), the `org`, `project`, `enterprise` and `content` modules, and the command-group wiring in `showcase.py` (`tests/test_cli_groups.py`: every contract name parses, `content social` writes the same file as the hidden, deprecated `social-preview` alias, writer jobs carry the contract keys). `tests/test_estate_corpus.py` runs only when `SHOWCASE_CORPUS_DIR` points at a local metadata corpus; it writes nothing into the package.

## Optional render gate

Chromium with Playwright is optional. When it is installed, the render gate captures animated intros at fixed times, checks the reduced-motion `.still` frame and renders arbitrary SVGs for contact sheets. Without it, `contact-sheet` accepts PNG, JPG and WebP inputs and SVGs that have a `--png` preview sibling, and exits 2 with a clear message for any other SVG.

## Visual review

Passing checks do not certify the look. View every new or changed banner, card, tile and intro on a contact sheet (`showcase.py contact-sheet`) on both GitHub page colours before it is committed, and compare the golden-configuration php2shell render with `assets/examples/banner-php2shell-golden.png`. Contact sheets are written as `NAME.on-github-dark.png` and `NAME.on-github-light.png` (proofing surfaces, never asset variants).
