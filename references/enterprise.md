# Enterprise module (decision 24)

The CompleteTech Enterprise is in scope. The skill stays **read-only toward GitHub**: it discovers the enterprise, snapshots it, checks the snapshot against the desired state in [`enterprise.yaml`](enterprise.yaml), and prints change records. The orchestrator's single writer queue runs approved API writes; the browser agent does UI-only work. The full research, procedure and guardrails are in the estate bundle's `audit/research/enterprise.md`; this page is the part an agent needs to run the module.

## Commands

```bash
gh auth refresh -h github.com -s read:enterprise,read:audit_log          # once; read scopes only
python3 scripts/showcase.py enterprise snapshot-query --slug SLUG       # print the validated read queries; runs nothing
python3 scripts/showcase.py enterprise discover                          # slug and id of each enterprise the viewer administers
python3 scripts/showcase.py enterprise snapshot --slug SLUG --out registry/enterprise.snapshot.json
python3 scripts/showcase.py enterprise doctor --snapshot registry/enterprise.snapshot.json [--baseline FIRST.json] [--approved FILE --approved-yaml FILE]
python3 scripts/showcase.py enterprise seat-check --snapshot registry/enterprise.snapshot.json [--user romgenie]
python3 scripts/showcase.py enterprise diff --baseline BEFORE.json --snapshot AFTER.json
python3 scripts/showcase.py enterprise plan --snapshot registry/enterprise.snapshot.json [--records changes.jsonl] [--jobs jobs.jsonl]
```

| Action | Network | Does |
|---|---|---|
| `snapshot-query` | none | Prints the validated Appendix A reads for a slug (`enterprise_discover`, `enterprise_snapshot`, `enterprise_drift`, `enterprise_romgenie` in `scripts/ctshowcase/queries/`) as `gh api graphql -F slug=… -F query=@FILE` argv, and which connections to page. For an operator or another agent that runs the reads itself. |
| `discover` | `gh api graphql` query | Lists the enterprises the viewer administers (`q_discover.graphql`). |
| `snapshot` | `gh api graphql` queries | Profile, billing counts, admins, domains, invitations, policy settings and rulesets (`q_profile`), plus every page of orgs, members and outside collaborators (`q_orgs`, `q_members`, `q_outside`). Records `taken_at`, slug, id and a sha256 per section. |
| `doctor` | none | E-checks on a snapshot (below). Exit 1 when a cell fails. Every org login in the snapshot goes through the shared resolver (CQ-03), so a renamed org (the snapshot shows `CompleteTech-Security` while `brand.yaml` may still key `CompleTetech-Security`) or a re-cased login counts in E5, E8 and E13; `--registry`, `--approved`, `--approved-yaml` and `--actions` point it at the approval files (default: the bundle beside the skill). |
| `seat-check` | none | E6 for one user: org roles, collaborator grants on private repositories, pending invitations. |
| `diff` | none | Identity, seats, orgs, owners, domains and policy settings between two snapshots (final-report tables). |
| `plan` | none | Change records for the profile and domain gaps, each with its `approval` id, the mutation file and its variables, plus the matching `scripts/writer.py` jobs (`jobs`; `--jobs FILE` appends them). Printed, never run. |

Every query file is checked for the word `mutation` before it is sent, and a test keeps it that way. Mutations live only in `enterprise/mutations/` and are referenced by `plan` records for the writer queue.

The `org`, `project`, `enterprise` and `content` groups are the skill's contract with the orchestrator; `snapshot-query`, `doctor` and `plan` are the contract's enterprise names, and `discover`, `snapshot`, `seat-check` and `diff` keep working beside them.

## Writer jobs

`plan` turns each record into a job with the shared contract `{id, phase: "1", kind: "enterprise", org: SLUG, approval_id, argv, note}`, plus `read` (the read-only `q_profile` query for the writer's before and after capture) and `idempotent`. The mutation is inline in `argv` (`gh api graphql -f query='mutation …' -f id=… -f name=…`), never loaded from a file, so the writer's guard sees it. The `approval_id` is the review-page row that approves it, the id `scripts/writer.py` looks up in `decisions/APPROVED_ACTIONS.yaml`: `ent-001` for the profile and `ent-002` for both domains (the `approvals:` map in `enterprise.yaml`). The record keeps its descriptive `approval` key (`enterprise/profile`, `enterprise/domain-add/<domain>`). The writer refuses the job until that row is approved; the guard also needs the `graphql <mutation> *` row that `scripts/build_approvals.py` writes for that review row. A domain add is followed by a user step (the DNS TXT record) before the verify job can succeed.

## Without the estate bundle

Nothing in this module needs the bundle: the desired state is [`enterprise.yaml`](enterprise.yaml) in the skill, the queries and mutations ship in the skill, and every offline action takes snapshot files by path. A synthetic snapshot for trying `doctor`, `seat-check`, `diff` and `plan` is `tests/fixtures/enterprise/snapshot-before.json`.

## Desired state

[`enterprise.yaml`](enterprise.yaml) holds the profile (§2.1 of the research: name `CompleteTech`, website `https://www.complete.tech`, location `Cincinnati, OH`, description as a proposal), the expected owners, the domains to verify at enterprise level (`complete.tech` and `www.complete.tech`), the seat to free (`romgenie`, decision 3), orgs that must never be inside (`MetatronAngelAgent`, decision 1) and the danger settings that must never change. It is separate from `brand.yaml` on purpose: an enterprise edit never changes the brand config hash that every repository's banner fingerprint includes.

## Doctor checks

| # | Check | Cell |
|---|---|---|
| E1 | Profile name, description, website and location equal `enterprise.yaml` | pass / fail |
| E2 | Custom avatar | manual (screenshot) |
| E3 | Enterprise README present (members only) | pass / warn |
| E4 | Every expected owner is an enterprise OWNER; two or more owners, or the user's break-glass choice recorded | pass / warn / fail |
| E5 | Each expected owner is OWNER of every in-scope org inside the enterprise | pass / fail |
| E6 | `seat_free_user` holds no org role, private collaborator grant or pending invitation inside | pass / fail |
| E7 | Every domain in `enterprise.yaml` is verified | pass / fail |
| E8 | In-scope orgs inside show the verified badge; each without one needs a reason code (`blog-other-domain`, `email-mismatch`, `email-blank`, `hold`, `outside-enterprise`) | pass / warn |
| E9 | Licenses used and purchased (reported for the before and after tables) | info |
| E10 | Danger settings unchanged since `--baseline` | pass / fail / unknown |
| E11 | Rulesets are only the approved ones | manual |
| E12 | Slug and id unchanged since `--baseline` | pass / fail / unknown |
| E13 | No out-of-scope, held or T3 org inside (it blocks every member-privilege policy) | pass / warn |
| E14 | UI-only settings match a dated screenshot | manual |

## Guardrails

- Policies are proposals only; each needs its own `enterprise` approval, and none is changed while E13 warns.
- Never: remove or transfer an org, change the slug, remove an enterprise member or admin, enforce 2FA, disable deploy keys, touch the IP allow list, SAML or notification restriction, change Actions permissions, or make a billing change.
- Free romgenie's seat org by org (enterprise teams first), never with "Remove from enterprise"; CompleteDotTech must be owner of each org first (E4, E5). Re-run `snapshot` and `seat-check` after each org.
- Enterprise writes need `admin:enterprise`; the writer adds it only for the approved step and removes it afterwards.
