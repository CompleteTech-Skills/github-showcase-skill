# Provenance and recorded-output checks

`provenance` records local evidence and prepares writer jobs. It never executes a
GitHub mutation. A stamp is not proof that an entire showcase workflow passed,
that a writer applied its jobs, or that anything was published.

The implementation is a maintenance design adopted under the repository campaign's
delegated engineering authority. It originated as the decision-25 proposal in
PR #200; it is not a verbatim user decision and does not override decisions 1–24.
In particular, the unchanged decision-18 footer remains the final README block.

## Commands and states

Pass an authorized metadata capture and an explicitly selected checkout or export
folder. Existing Git checkouts must prove their target identity; a different or
unverifiable origin is refused. Every output path and ancestor is checked before
reading or writing. Symlinks, unsafe relative paths and output/queue collisions
cannot establish provenance.

```sh
python scripts/showcase.py --meta CAPTURE.json --repo-dir CHECKOUT \
  provenance check OWNER/REPO --offline --format json
python scripts/showcase.py --meta CAPTURE.json --repo-dir CHECKOUT \
  provenance stamp OWNER/REPO --offline --format json
```

Targets also accept `org:ORG`, `user:LOGIN` and `enterprise:SLUG`. An Enterprise
check requires a supplied `--snapshot` and the private registry source; it never
emits a public repository job. Org/profile About evidence must be known before
their recorded outputs can be considered fresh. An offline capture with missing
About fields remains incomplete.

| Status | Exit | Meaning |
|---|---:|---|
| `never` | 1 | No stamp or prior generated-output evidence was found. |
| `untracked` | 1 | Prior generated material exists without a provenance stamp. A backfill records available evidence, including its gaps. |
| `incomplete` | 1 | A stamp exists, but required captured inputs or output evidence are missing, unknown or pending. |
| `stale` | 1 | Recorded input, configuration or output bytes have changed, or the stamp is invalid. |
| `fresh` | 0 | The explicitly recorded outputs match the supplied inputs and current bytes within the reported verification scope. |
| `foreign` | 2 | Owner/consent, target identity or provenance ownership refuses this target. |

Usage errors also return 2; missing source access and other required operator
inputs return 4. `--from-file FILE` checks one target per line, spaces permitted
GETs by `--delay`, and stops on rate limiting. Batch exit 4 means required input
is unavailable, otherwise exit 1 means work remains.

Every result reports `verification_scope: "recorded-outputs"` and `skip: false`.
Do not skip a whole target because its stamp is fresh. `changed[]` contains reason
codes; `missing[]` names absent or unverified evidence; `rerun[]` contains canonical
source-relative paths to review or regenerate. These are diagnostic inputs to
the ordinary eligibility, doctor, lint, art-review and approved-writer workflow.
They are not an executable partial-run plan.

## Evidence and locations

| Target | Stamp | Required recorded evidence |
|---|---|---|
| Repository | `docs/images/.showcase.json`, preserving existing generator fields | Managed README; applicable banner/card receipts and actual bytes, or supported explicit exemptions; all additional recorded artifacts; complete supplied metadata. |
| Organization | `.github/showcase.json` in the selected `ORG/.github` source | `profile/README.md`, `profile/data.json`, referenced local art and known About fields. |
| Personal profile | `.github/showcase.json` in the selected `LOGIN/LOGIN` source | `README.md`, `data.json`, referenced local art and known About fields. |
| Enterprise | `<estate root>/registry/enterprise.showcase.json` | Actual private `enterprise.snapshot.json` bytes and supplied snapshot sections for profile, organizations, members and outside collaborators. |

The [schema](provenance.schema.json) validates the `provenance` identity,
version, target, timestamps, run count and fingerprint. A sibling `evidence` block
records version 1, the bounded scope, known inputs, configuration digest, output
digests or supported exemptions, missing reasons and pending writer state.
Legacy stamps without this evidence remain readable but cannot certify freshness.
Staged descriptions and stale generator receipts remain incomplete until reconciled.

The stamp's timestamps and count stay outside the rendering fingerprint. An
ordinary `--changed auto` or `--changed no` capture without `--force` writes
nothing when its recorded evidence is unchanged, even if the checkout still has
the same uncommitted changes. This applies to fresh and incomplete captures. A
changed README is a recorded output change and advances `last_changed_at`.

The existing explicit controls have separate meanings: `--force` requests a new
local observation timestamp even for unchanged evidence; `--changed yes` asserts
that this run has other changes to accompany its stamp. They retain their
documented last-run/count behavior and never turn missing or pending evidence
into completed work. `--changed no` does not suppress a genuine recorded-output
change. The CLI never commits files, and these controls do not authorize a
standalone timestamp-only commit. The Action records evidence in the same local
change set as its art, does not forward provenance `--force`, and never changes
its commit boundary merely to update a timestamp.

`stamp --jobs FILE` prepares a pending writer job. Pending jobs are never proof of
execution and do not count as completed local captures. Queue preflight occurs
before writes. Preserve the writer's approval and expected-blob checks, then
capture and verify the resulting state separately after an authorized writer runs.
The optional `--propose-topic` remains off by default and produces an approval
requiring writer job; it never adds a topic itself.

## Credit and operator ledger

Configured skill credit sits in its own `showcase:credit` block immediately
**before** the unchanged final decision-18 footer. The footer stays the only
`<picture>`. The credit includes a `generated-by: github-showcase-skill` marker
and the configured visible attribution line. Footer/readme lint requires the
credit when attribution is configured.

Ownership requires the entire configured credit, with only equivalent HTML
formatting and an older version allowed. Another generator, extra authored text,
different links or ambiguous inline seams are not owned; generation refuses
before any write. An old footer without credit gains it on refresh. A proven
post-footer credit from the original proposal moves before the footer on a normal
header refresh; `--no-regroup` refuses that order change.

The operator ledger stores counts and star-state fields, never target names or
telemetry. It lives in `$SHOWCASE_STATE_DIR/state.json`, otherwise the platform's
documented application-config directory. Only a verified local `provenance stamp`
capture counts; incomplete captures and pending writer jobs do not. This count is
not evidence of a live rollout or whole-workflow completion. CI records no runs.

At five counted captures, an explicitly online interactive text invocation may
make a read-only star-status GET. A known not-starred result may print one optional
line, then at most once per five further captures (5, 10, 15, ... when eligible). Unknown failures stay unknown
and silent. A starred result or `provenance star --decline` stops future prompts.
The skill never stars a repository on the operator's behalf.

`--offline` guarantees no network call, including this ledger path. JSON mode,
quiet mode, CI, a non-TTY, `--no-star-prompt` and `SHOWCASE_NO_STAR_PROMPT=1` suppress
the prompt. `SHOWCASE_STAR_PROMPT` cannot override these rules. Agents do not relay
marketing text from unattended runs.
