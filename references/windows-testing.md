# Windows test portability

Use the project virtual environment's Python to run `python -m pytest -q`.
The CLI emits UTF-8 on every platform. The test CLI helper decodes UTF-8 explicitly;
fixtures and generated Markdown used by these regressions are also read and written
as UTF-8. This avoids depending on a developer's Windows ANSI code page.

Action shell tests carry the `requires_bash` marker. On Windows the helper locates
`bin/bash.exe` or `usr/bin/bash.exe` beside the Git for Windows installation, rather
than invoking Windows' `bash.exe` WSL launcher. When `git` is a package-manager shim,
the helper uses read-only `git --exec-path` to find the actual installation. On POSIX it uses `bash` from `PATH`.
It sends shell source over stdin, so Windows command-line parsing cannot expand or
strip the script's quotes. Action paths use forward slashes, including paths with
spaces. Tests execute the real Action shell code and use `SHOWCASE_DRY_RUN=1` when
testing commits; they never push or open a PR.

If that shell is absent, only the marked Action shell tests skip, with an explicit
reason to install Git for Windows or POSIX bash. Other tests continue. Installing or
restarting WSL is unnecessary. The `Test portability` workflow runs the full suite
on Windows, Linux and macOS, in addition to the existing package and quality gates.

## Issue #9 triage

All 15 historical failure cases were reproduced after the UTF-8 CLI fix in #8.
The corrections below preserve their assertions and run them on Windows; none was
blanket-skipped.

| Test | Cause and correction |
|---|---|
| `test_action.py::test_commit_script_dry_run` | WSL launcher misparsed a Windows script path; use Git Bash and stdin. |
| `test_banner.py::test_text_column_chips_and_bar` | UTF-8 CLI bytes decoded as CP1252; decode CLI capture explicitly. |
| `test_content.py::test_icon_prompt_needs_writer_then_ok` | UTF-8 art-direction fixture decoded as CP1252; read it as UTF-8. |
| `test_meta_recency.py::test_meta_from_gh_t3_needs_allow_t3_and_records_recency` | Extensionless POSIX `gh` stub was not a Windows executable; stub the subprocess transport in-process and still assert GET-only argv, T3 refusal and recency capture. |
| `test_readme_upgrade.py::test_renames_and_notes` | CP1252 cannot write the sparkle in the fixture; write UTF-8. |
| `test_readmelint.py::test_pass_then_each_failure` | Generated footer and navigation were written with CP1252; preserve UTF-8 across fixture writes/reads. |
| `test_readmelint.py::test_incomplete_only_needs_input` | Same generated-Markdown encoding mismatch; preserve UTF-8. |
| `test_review_action_commit.py::test_template_icon_removal_is_committed` | WSL launcher script path mismatch; execute through Git Bash. |
| `test_review_action_commit.py::test_only_the_icon_deletion_is_swept` | Same shell mismatch; real deletion/staging assertions retained. |
| `test_review_action_commit.py::test_own_icon_is_kept_and_unstaged_edits_untouched` | Same shell mismatch; real preservation assertions retained. |
| `test_review_links_r2.py::test_footer_logo_urls_are_not_this_repository_under_a_former_owner` | UTF-8 footer decoded as CP1252; read Markdown as UTF-8. |
| `test_review_round1_integration.py::test_action_skips_a_held_readme_instead_of_failing` | Windows parsing of multiline `bash -c` source expanded shell content prematurely; stream it to Git Bash. |
| `test_review_round2_integration.py::test_action_fails_on_a_readme_config_error` | Same multiline shell quoting mismatch; stream source and preserve the configuration-error assertion. |
| `test_review_round2_integration.py::test_upgrade_keeps_a_partner_logo_in_a_credited_block` | UTF-8 generated footer decoded as CP1252; read UTF-8 before the duplicate-footer assertion. |
| `test_round1_regressions.py::test_lint_all_fails_a_missing_banner` | Slash-only basename split failed on Windows paths; use `Path.name`. |

Additional regressions force a legacy parent locale for CLI capture, distinguish
Git Bash from the WSL launcher, and exercise nested shell quoting and paths with spaces.
The remaining baseline encoding failures resolved in #8 are tracked by that PR.

Clean Linux testing also exposed an older Python 3.12 `argparse` behavior: a lint
filename after `--kind` could be rejected even though newer Python versions accept
it. Lint now accepts those file operands while still rejecting unknown options;
the same command-order regressions run on all supported platforms.

The new macOS full-suite job also exposed Bash 3.2 treating an empty optional
argument array as unset under `set -u`. The Action uses guarded array expansion
for that shell, and its integration test covers both an empty and populated
optional-argument array.
