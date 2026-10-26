# Examples

This directory holds runnable example inputs and overrides for this skill. Every input is synthetic (the fictional demo client Northwind Trading Co.) or copied from a public repository; nothing here comes from a private repository.

Rendered demonstration artifacts live under `assets/examples/` so README previews and packaged outputs stay close to the visual assets they reference.

| Path | What it is |
|---|---|
| `meta/northwind-support-triage-agent.json` | Synthetic metadata for a Northwind Trading Co. CLI repository (the skill's `example_inputs`) |
| `meta/northwind-cve-2026-00001-check.json` | Synthetic metadata in the security-check shape: a CVE slug and its key chip |
| `meta/github-showcase-skill.json` | Pre-publish metadata for this skill, used for its own README banner and card |
| `repos/` | Small synthetic or public-shaped checkouts for `--repo-dir`: manifests, an `assets/icon.png`, a `.github/showcase.yml` |
| `orgs/` | An org avatar for the org-tile example |
| `estate/` | A synthetic estate for the `org` command group: `registry/estate.yaml` (Northwind Trading Co. only, same layout as the private estate registry) and `meta/` (one metadata file per repository, including a private one that must never reach the public profile) |
| `showcase.yml` | An annotated example `.github/showcase.yml` override (content only: icon, subtitle, chips, category, variant) |
| `render_examples.sh` | Regenerates every committed preview in `assets/examples/`, the contact sheets, and `docs/images/` |

## Run every command on the fixtures

Run from the skill root after `python -m pip install -r requirements.txt`. `--repo-dir` points at a fixture checkout; `--no-repo-dir` renders from the metadata alone.

```bash
M=examples/meta/northwind-support-triage-agent.json
D=examples/repos/northwind-support-triage-agent
C="python scripts/showcase.py --meta $M --repo-dir $D"

# checks (JSON verdicts and proposals; nothing is written to GitHub)
$C describe
$C topics --gh
$C labels --plan --gh
python scripts/showcase.py labels --emit-yml

# generators
$C banner --out output/banner.png
$C card --out output/card.svg --png output/card.png
python scripts/showcase.py intro --profile CompleteDotTech --static --out output/intro.svg
python scripts/showcase.py org-tile --org CompleteTech-Skills --avatar examples/orgs/CompleteTech-Skills/avatar-500.png --out output/tile.svg --png output/tile.png
python scripts/showcase.py footer

# README (dry run prints a unified diff)
$C readme --mode auto --diff

# lint, coverage and the set review
python scripts/showcase.py lint svg --kind card output/card.svg
python scripts/showcase.py lint svg --kind intro output/intro.svg
python scripts/showcase.py lint banner output/banner.png
$C doctor --header
python scripts/showcase.py contact-sheet output/banner.png --mode stack --out output/sheet
```

## Org, project, enterprise and content commands

```bash
E="SHOWCASE_ESTATE_ROOT=examples/estate"
env $E python scripts/showcase.py org about Northwind-Trading-Co --jobs output/jobs.jsonl
env $E python scripts/showcase.py org profile Northwind-Trading-Co --meta-dir examples/estate/meta --out-dir output/dotgithub
env $E python scripts/showcase.py org pins Northwind-Trading-Co --jobs output/jobs.jsonl
env $E python scripts/showcase.py org labels Northwind-Trading-Co --meta-dir examples/estate/meta --jobs output/jobs.jsonl
env $E python scripts/showcase.py org doctor Northwind-Trading-Co --meta-dir examples/estate/meta --doctor-format tsv --header
python scripts/showcase.py project normalize --capture tests/fixtures/project/reference-capture.json
python scripts/showcase.py project lint --capture tests/fixtures/project/reference-capture.json --owner Northwind-Trading-Co
python scripts/showcase.py enterprise snapshot-query --slug northwind
python scripts/showcase.py enterprise plan --snapshot tests/fixtures/enterprise/snapshot-before.json --jobs output/jobs.jsonl
$C content links
$C content linguist
$C content social --out output/social-preview.png --job
```

`org profile` writes `profile/README.md` and `profile/data.json` under `--out-dir` only after its leak check passes: the private `private-pricing-engine` repository and the registry's `why` notes never appear in them. `project lint` exits 1 on the reference capture by design (it is not yet a §13 board). Every planned GitHub change lands in `output/jobs.jsonl` as a `scripts/writer.py` job; nothing is sent to GitHub.

On this fixture `labels --plan` and `doctor` exit 1 by design: the synthetic repository still has GitHub's default labels and no `assets/icon.png`, so the plan lists the renames and creates, and the coverage row shows the failing cells.

The security-check fixture exercises the CVE key chip and the security subtitle rule:

```bash
python scripts/showcase.py --meta examples/meta/northwind-cve-2026-00001-check.json --no-repo-dir card --out output/cve-card.svg --png output/cve-card.png
```

`repos/php2shell-check/.github/showcase.yml` reproduces the golden php2shell-check banner (two CVE key chips, one attribute chip, a short subtitle); `bash examples/render_examples.sh` renders it to `assets/examples/banner-php2shell.png` (with the Security org's mark) and, with `--icon assets/brand/logo.png`, to `assets/examples/banner-php2shell-golden.png` (the golden's white card).

Outputs under `output/` are ignored by git. Committed previews in `assets/examples/` and `docs/images/` are regenerated with `render_examples.sh`, never edited by hand.
