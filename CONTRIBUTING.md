# Contributing to CompleteTech LLC Skills

[Start here](ONBOARDING.md) · [Branding and handoffs](BRANDING.md) · [Maintainer instructions](AGENTS.md) · [Specialist instructions](SKILL.md)

## Compatibility

Keep each skill independently usable. Preserve activation keys, root generator CLIs, templates, runtime dependencies, consent and approval gates. The ledger's standard-library core and neutral branding are intentional differences, not gaps to remove.

## Verification

From a full checkout using Python 3.12, the package CI baseline:

```bash
python -m unittest discover -s tests -p 'test_package_*.py' -v
python scripts/validate_package.py
```

Also run the existing quality and regression commands in [README.md](README.md). Package checks are read-only and do not execute specialist generators. They validate metadata, required files, local documentation links and PNG chunk integrity, not decoded artwork or document truth. Do not weaken original Quality checks to obtain a green result.

## Coordinated changes

Keep `skill-package.json`, onboarding and actual entry points synchronized. Shared validator, tests, CI, maintainer instructions and branding guidance must match the orchestrator's shared-file audit. Use focused PRs and report exact checks, failures and limitations. Respect branch protection, review requirements and changed heads.

Use synthetic fixtures and new output paths instead of overwriting committed previews. Never commit secrets, personal logs, real account mappings, client documents or unapproved quotes. Code remains under [LICENSE](LICENSE); branding remains under [BRAND_ASSETS.md](BRAND_ASSETS.md). Do not redistribute private assets or fonts. Registry releases and repository visibility changes require separate authorization.

## Changing this skill

The full gate for this repository adds the test suite and the showcase quality gates to the package baseline:

```bash
python -m pip install -r requirements.txt ruff==0.17.2 pytest==9.1.1
python -m pytest -q
python scripts/validate_quality.py
```

- **Standard data** lives in `references/brand.yaml` and `references/standard/`. Change a rule there, not in code, then regenerate the stdlib lock copy with `python scripts/showcase.py config --write-lock` (the quality gate checks that it is in sync).
- **Rules a user decision settled** (dark-only art, banner first, the exact footer) change only after the user changes the decision; see [references/decisions.md](references/decisions.md).
- **Generators** must stay deterministic: rendering the same inputs twice gives byte-identical files. Add a regression test for every layout change, and compare the php2shell render against the golden layout mask.
- **Fixtures** are synthetic (Northwind Trading Co.) or copied from public repositories only. Never copy metadata, names or README text from a private repository into `tests/` or `examples/`.
- **Previews** in `assets/examples/` and `docs/images/` are regenerated with `scripts/showcase.py`, never edited by hand. View them on a contact sheet before committing.
