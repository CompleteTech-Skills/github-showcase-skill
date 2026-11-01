# T3 sign-off records (`--allow-t3` needs one)

`--allow-t3` is enforced by default: the tool verifies the operator's claim that a co-owner signed off against a record file. There is no opt-out: no flag or environment variable turns the check off. A T3 run therefore needs a valid, unexpired record that covers the owner and, when the record is scoped, the repository.

## Where the file lives

The canonical private path is `<estate_root>/decisions/t3-signoffs.yaml`, where the estate root is `resolver.estate_root()`: `SHOWCASE_ESTATE_ROOT` when set, otherwise the skill's parent bundle. The order is the explicit `--t3-signoff-file PATH`, then `SHOWCASE_T3_SIGNOFF_FILE=PATH`, then the canonical path. When no estate root resolves there is no default path and the refusal is `t3-signoff:no-file` saying so; the flag is never trusted instead. The tool reads the file and never creates it. The records belong in the private estate bundle (issue 24: tracked there, never copied into target repositories). Never copy a record into a repository. Real records come only from the estate bundle; the files under `tests/fixtures/t3-signoff/` are synthetic.

## Format

The contract is [t3-signoff.schema.json](t3-signoff.schema.json). YAML dates are written bare (`2099-12-31`); convert them to ISO strings before validating with a generic JSON Schema validator. `scripts/ctshowcase/signoff.py` checks the same rules (`problems()`): a string date or timestamp must match the schema's `date` or `awareTimestamp` pattern before it is parsed, so compact (`20991231`) and week (`2099-W52-1`) forms are invalid in both. The one deliberate difference is that a pattern-shaped but impossible date (`2099-02-30`) is also invalid in the tool. Tests keep the two in step, including one that applies the schema's patterns without needing `jsonschema`.

```yaml
signoffs:
  - id: t3s-001                # carried onto writer jobs and change records as signoff_id (approval_id is never set from it)
    owner: Example-Co-Owned    # any login of the org; renamed logins resolve through its aliases
    repos: ["*"]               # "*" (also needed for owner-wide actions), repository names, or OWNER/NAME
    approved: true             # a boolean; only true grants
    approver: example-co-owner # who signed off
    approved_on: 2026-01-15    # the date they signed off (not in the future)
    expires: 2099-12-31        # not before approved_on; a date (valid through that day) or a timestamp with a UTC offset (valid before that instant)
    note: "optional free text"
```

| Field | Required | Rule |
|---|---|---|
| `id` | yes | non-empty string |
| `owner` | yes | non-empty string |
| `repos` | yes | `"*"`, a name, or a non-empty list of names / `OWNER/NAME` |
| `approved` | yes | boolean (`"true"` as a string is invalid) |
| `approver` | yes | non-empty string |
| `approved_on` | yes | date `YYYY-MM-DD`, not later than today (a sign-off that has not happened yet grants nothing) |
| `expires` | no | optional; absent means no expiry. When present: date `YYYY-MM-DD`, or a timestamp with `Z` or `+HH:MM`; a timestamp without an offset is invalid; not earlier than `approved_on` |
| `note` | no | string |

No other fields are allowed. The file itself is an object with the one key `signoffs`, a list of record objects; a top-level list, any other top-level key or a non-object entry makes the whole file authorize nothing (`t3-signoff:missing`), as the schema refuses it.

## Refusals

Each refusal exits 2 with result `refused`.

| Log | Meaning |
|---|---|
| `t3-signoff:no-file` | no record file was found; the log names the resolved path |
| `t3-signoff:missing` | no approved record for the owner (also an unreadable or non-YAML file, or a file whose envelope breaks the schema) |
| `t3-signoff:invalid` | the owner has no usable approved record and a malformed one is the cause (it breaks the schema, has `approved_on` in the future or `expires` before `approved_on`, or `expires` is null or unparseable), or a malformed `repos` (not `"*"`, a name or a non-empty list of names) is on the owner's record, which is always reported as invalid and never as `scope`, even beside a valid grant for an unrelated repository; the error names the record id and the first problem. Two records with one id are also invalid. A malformed `approved: false` record (an extra key, an `approved_on` with a time part, a non-string `note`, a malformed `repos`) that could cover the request is also `t3-signoff:invalid` and never leaves a grant standing; one clearly for a different named repository does not block |
| `t3-signoff:scope` | the owner has valid approved records but none covers the repository; an `OWNER/NAME` repository is covered only when that owner is the record's org (only `*` covers another account's repository) |
| `t3-signoff:expired` | every covering record is past `expires` |
| `t3-signoff:revoked` | every otherwise-grantable record was withdrawn, for the requested repository, by a later or same-day `approved: false` record (see Withdrawal) |

## Withdrawal

The file is append-only, so no edit of the original grant is needed. An `approved: false` record for the same owner, with `approved_on` on or after a grant's `approved_on` (the same day counts; an earlier date does not), vetoes that grant for every repository the withdrawal covers (`*` covers all). The veto is per repository, so a co-owner can withdraw one repository from a `*` or multi-repository grant: grant `[a, b]` plus withdrawal `[a]` refuses `a` with `t3-signoff:revoked` and still grants `b`. Repositories compare as the same when written as a bare `NAME` or as `OWNER/NAME` under the owner or any of its aliases (a grant for `site` is withdrawn by `OWNER/site` and the reverse), while `OTHER/NAME` for another account stays distinct. A new `approved: true` record dated after the withdrawal grants again. A withdrawal that is malformed (it breaks the schema, for example an extra `reason` key) and could cover the request is never ignored: the run refuses `t3-signoff:invalid` naming the record id and the first problem, so a mistyped withdrawal never leaves a grant standing. A record for the owner whose `approved` is not a boolean (the string `"false"` or `"true"`, `0`, `1`, `null` or a missing key) is likewise a possible withdrawal that fails closed as `t3-signoff:invalid`; it is never coerced into a grant or a withdrawal.

An owner-wide command (`org profile`, `org pins`, `project estate-plan`) is gated once for the owner, and a `*` grant with a later withdrawal of some repositories stays valid for the owner, so the per-repository check is repeated where a repository is named or acted on. With `--allow-t3`, `org profile` omits a repository of a T3 org whose own sign-off is not granted (featured, sections, forks, archives) and `org pins` holds its pin (check result `hold`, no pin job, not in the order job), each logging `t3-signoff:<code>:<login>/<repo>`; the org's other repositories keep the grant's `signoff_id`. `project estate-plan --allow-t3` also reads the Org options already captured on the board: a captured option naming a T3 org without a valid record holds the Org option update and the README (no option id is deleted) and logs `t3-signoff:<code>:<login>` with `hold:org-options`.

**`signoff_id` and `approval_id` (issue #26).** Task #26 says "add `approval_id` to jobs created under the flag". This implementation names the sign-off in a separate `signoff_id` (`signoff_ids` for several) and never sets `approval_id`, because `approval_id` names the `decisions/APPROVED_ACTIONS.yaml` row the writer guard looks up, and a sign-off id is not one. Read #26 as "carry the sign-off id as `signoff_id`".

`project estate-plan --allow-t3` omits every T3 org that has no valid record and records `t3-signoff:<code>:<login>` (code `missing`, `expired`, `scope`, `revoked` or `invalid`) in the plan's `logs` for each one, so the operator sees why the org is absent.

Excluded owners (`exempt`) and HOLD owners (`hold`) are refused before the record is read. Repository `doctor` stays read-only: it reports R7 `hold` instead of refusing, and with `--allow-t3` shows the granting record as `signoff_id`.

The owner checked is also the one that holds the repository today: a repository named under one org whose approved pending transfer resolves to a T3 org is gated as that T3 org's (org label jobs, profile home repositories, favorites and star-List items). A T3 org's association carries that org's record id (`signoff_id`; `signoff_ids` lists every id when more than one record applies, for example a star-List item job that adds a T3 repository to a T3 org's List carries the favorite's record and the List org's record): the topics change record of `topics --also-in`, the topics job and change record of `adopt` for a repository whose metadata lists the org in `also_in`, and the `project estate-plan` jobs that put the org in the personal board's Org field (its `orgs` entry shows the id too). Jobs and change records carry `signoff_id` (and `signoff_ids`). `approval_id` is left untouched, because it names the `decisions/APPROVED_ACTIONS.yaml` row the writer guard looks up; a job's existing `approval_id` is kept and a sign-off id is never written into it.

Project settings pass (`project copy-plan --allow-t3`, §13.9 step 7): the 'Default repository' and 'Auto-add to project' browser steps name only a repository that passed its own sign-off check (the first link actually emitted), never a withdrawn, unauthorized or other-owner one. When repositories are listed but none is authorized, the settings job is held and the plan logs `settings-held:default-repository-and-auto-add`. The settings job carries `signoff_id` (and `signoff_ids`) of the record that grants the repository it names, like the link jobs.

Copy-plan sign-off scope: the per-repository authorization is decided once, before any job names a repository. The README job (links and default repository), the auto-add step of the `-workflows` browser job and the settings job all follow it. A withdrawn or unauthorized repository, whether from `--repos` or only captured in the board's README, appears in none of them. When no repository is authorized the auto-add step is omitted (`workflows-held:auto-add`). Each of these jobs carries the granting `signoff_id` of the repository records it names, so a later repository-specific regrant is stamped instead of the cached wildcard grant. Standalone `project readme` generation is unchanged.
