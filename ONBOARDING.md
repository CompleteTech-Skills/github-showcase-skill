# Start here: github-showcase-skill

<p align="center"><img src="docs/images/banner.png" alt="github-showcase-skill by CompleteTech LLC" width="100%"></p>

**CompleteTech LLC Skills** · README hero banners, repo cards and estate checks; never a GitHub write.

[Overview](README.md) · [Agent instructions](SKILL.md) · [Contributing](CONTRIBUTING.md) · [Skill library](https://github.com/CompleteTech-Skills/agentic-services-orchestrator-skill/blob/main/references/skill-family.md)

## 1. Choose the right skill

This is a `catalog-renderer` in the CompleteTech Skills family. Its install/activation key is **`github-showcase-skill`**. Use it whenever a CompleteTech-family repository, README, org, org profile, GitHub Project board, the CompleteTech Enterprise or the profile page must match the estate standard: it generates the art and checks the metadata, and it hands every proposed GitHub change to a writer instead of applying it. Use the orchestrator when work spans multiple specialists. Install the complete skill directory, including `SKILL.md`, references, scripts and assets, in the directory supported by your agent. Do not install only the Markdown file. Keep this skill separate from its siblings.

## 2. Get a full checkout and prepare Python

Python 3.12 is the shared CI baseline. Git is needed only for cloning. The full GitHub checkout includes the brand files and the OFL fonts the generators need; the text-only ClawHub bundle omits them (see [CLAW_HUB_PUBLISHING.md](CLAW_HUB_PUBLISHING.md)).

```bash
git clone https://github.com/CompleteTech-Skills/github-showcase-skill.git github-showcase-skill
cd github-showcase-skill
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/validate_package.py
python scripts/showcase.py fonts --check
```

On Windows PowerShell, create the environment with `py -3 -m venv .venv`, then use `.\.venv\Scripts\python.exe` instead of `python` in subsequent commands. Activation is optional; do not change machine execution policy for this skill. For an existing checkout, skip `git clone` and start at environment setup.

The CLI writes UTF-8 to stdout and stderr, including redirected Windows output. When
capturing output from Python, use `subprocess.run(..., encoding="utf-8")`. No
`PYTHONIOENCODING` override is required for non-ASCII JSON, footer text or diagnostics.

## 3. Run a safe demonstration

Run from the skill root. The commands below use the bundled synthetic Northwind Trading Co. metadata and a small synthetic checkout in `examples/repos/`, not a real repository, and name that checkout with `--repo-dir`. On a real repository, run `python3 <skill-dir>/scripts/showcase.py` from inside the repository's checkout instead: with `--meta` and no `--repo-dir`, the command refuses (exit 2) unless the current directory is the checkout the metadata describes, so it never writes into the skill. Outputs go to `output/`, which git ignores; choose new filenames when retaining earlier output.

```bash
M=examples/meta/northwind-support-triage-agent.json
D=examples/repos/northwind-support-triage-agent
python scripts/showcase.py --meta $M --repo-dir $D describe
python scripts/showcase.py --meta $M --repo-dir $D topics
python scripts/showcase.py --meta $M --repo-dir $D banner --out output/onboarding-banner.png
python scripts/showcase.py --meta $M --repo-dir $D card --out output/onboarding-card.svg --png output/onboarding-card.png
python scripts/showcase.py lint svg --kind card output/onboarding-card.svg
python scripts/showcase.py lint banner output/onboarding-banner.png
python scripts/showcase.py contact-sheet output/onboarding-banner.png --mode stack --out output/onboarding-sheet
```

`describe` and `topics` print JSON verdicts and proposals; nothing is written to GitHub. The banner and card are rendered from the fixture's description and topics. The synthetic checkout has no `assets/icon.png`, so the banner falls back to the brand logo and logs `needs-input:repo-icon`; that log is expected. Pass `--no-repo-dir` instead of `--repo-dir` to render from the metadata alone.

The `org`, `project`, `enterprise` and `content` command groups print plans and `scripts/writer.py` jobs instead of art. Try them offline on the synthetic estate: `SHOWCASE_ESTATE_ROOT=examples/estate python scripts/showcase.py org profile Northwind-Trading-Co --meta-dir examples/estate/meta`, then `python scripts/showcase.py --meta $M --repo-dir $D content links`. [examples/README.md](examples/README.md) lists a first command for every group.

## 4. Inspect the outputs

Open `output/onboarding-banner.png` and the two contact sheets (`output/onboarding-sheet.on-github-dark.png` and `output/onboarding-sheet.on-github-light.png`). Check the eyebrow, the slug, the subtitle, the chips and the accent bar at both README widths, and confirm that nothing is clipped. Open `output/onboarding-card.png` at 400 px wide. Package validation checks structure; it does not certify visual quality or factual correctness. Committed previews in `assets/examples/` are references, not destinations for your first run.

## 5. Use the skill with your agent

Read [SKILL.md](SKILL.md), select `github-showcase-skill` using your agent's skill activation mechanism, and provide the repository checkout, its metadata (or permission for read-only `gh api` GETs), the requested outputs and the approval owner for any GitHub change. Agent discovery paths differ by product; follow that product's installation documentation rather than assuming one global path. Do not grant broader permissions simply because multiple skills are installed together.

For a new repository, start from `completetech-repo-template`: its workflow calls this skill's composite Action, which bootstraps the README for the detected type and keeps the banner and card current.

## Branding and handoff

Use the committed CompleteTech LLC brand files and the practical, evidence-led voice described in [README.md](README.md). The code license does not grant logo, seal or signature rights: follow [BRAND_ASSETS.md](BRAND_ASSETS.md). Do not replace or republish private artwork or fonts. Every surface uses the dark design (decision 21); do not add light variants.

For a multi-skill handoff, preserve the source facts, artifact paths, `logs[]` codes, change records, approval owner/status, blockers and next specialist in the orchestrator's existing `project_state` schema. Do not treat a generated banner, a passing lint or a clean `doctor` row as permission to push, publish or change repository settings.

## Safety and permissions

The documented generation workflow is local. Installation may contact GitHub and package indexes. `meta --from-gh` and the opt-in `org labels ORG --repos-from-gh` mode make read-only `gh api` GETs. `fonts --fetch` downloads the pinned fonts. Org-wide label planning emits proposed jobs for review; it never applies them. Generation does not push commits, change descriptions, topics, labels or settings, publish documents, grant approval or install background services. T3 (co-owned) owners are refused unless `--allow-t3` is passed for one approved invocation; the claim is checked by default against a sign-off record in the private estate bundle (`decisions/t3-signoffs.yaml`, or `--t3-signoff-file PATH`; there is no opt-out) ([references/t3-signoff.md](references/t3-signoff.md)). Keep real sign-off records in the private estate bundle; never copy them into a repository. Review the boundaries in [SKILL.md](SKILL.md) before using real repositories.

## Troubleshooting and verification

A missing module usually means the active interpreter differs from the one used for `pip`; use `python -m pip` in the same environment and this repository's `requirements.txt`. Missing fonts, logos or references usually indicate a partial/text-only installation or the wrong working directory; use a full checkout and run from its root, or run `python scripts/showcase.py fonts --fetch`. Do not download replacement branding from unrelated sources. Exit code 3 (`art-fail`) means text did not fit the fixed size ladder; shorten the source text or set a `subtitle` in the repository's `.github/showcase.yml`, never truncate it.

```bash
python -m unittest discover -s tests -p 'test_package_*.py' -v
python scripts/validate_package.py
```

These checks use the standard library and do not execute the listed generators, scan accounts, contact services or install schedules. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [QUALITY.md](QUALITY.md) for the additional runtime, rendering, parser and diagram checks.
