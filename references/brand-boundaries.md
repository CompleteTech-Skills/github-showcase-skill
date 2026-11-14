# Brand identity and legal wording

An organization's family supplies its visual identity. A co-owner's permission to
run a command does not supply a missing palette or mark. The TicketStub family is
marked `identity_pending: true`: its generators return `needs-input:brand-identity`
until owner-supplied identity data is configured, even with `--allow-unmeasured`.
Without T3 sign-off, the existing consent refusal still takes precedence.
Repository commands check the grant against that repository before reporting
missing identity inputs; organization surfaces require an organization-wide grant.

Each organization has optional legal wording fields in `references/brand.yaml`:

- `license_wording`: exact reservation text appended to a factual public license reference.
- `skills_license_wording`: exact reservation text used when `BRAND_ASSETS.md` exists;
  it falls back to `license_wording`.
- `private_license_wording`: the complete private license section. An explicit
  `<year>` placeholder uses the repository's captured creation year; a missing year
  returns `needs-input:license-year`.

Absent wording never grants permission to infer trademark or copyright claims
from a display name, tier or family. Public repositories retain a factual reference
to their captured license and `LICENSE`; private repositories without explicit
wording do not receive a generated license section. Both cases log
`needs-input:license-wording`. Existing authored license text remains subject to the
README preservation rules. The CompleteTech rows explicitly retain the previously
configured CompleteTech wording. The synthetic Northwind row is a demonstration of
that policy, not a statement about a real business.

README badges use each family's configured badge colours instead of inheriting
CompleteTech blue.

Captured SPDX, supporting file presence and configured policy are separate inputs.
README badges use captured SPDX for public and private repositories; private
visibility does not imply proprietary licensing. Missing SPDX logs
`needs-input:license` and omits a new badge. Exact private wording remains an
explicit section control and is never parsed to derive a badge or a commercial
grant. Blank identifiers are unavailable; a non-string
identifier (including a non-string nested `spdx_id` or `key`) refuses the command
with `needs-input:license` before writing. Captured string identifiers are trimmed.
The Internal / distribution callout is unchanged presentation policy.

The configured AGPL/commercial README policy requires a captured AGPL-3.0
identifier and both `LICENSE` and `LICENSING.md` before its standard badge and
paragraph are generated. A variant alone cannot supply the policy. Contradictory
policy/SPDX logs `needs-input:license-policy`; missing supporting files log
`needs-input:license-file` or `needs-input:licensing-file`. Retain factual SPDX
without unsupported references, preserve authored sections and request owner
reconciliation. The tool never changes licenses or decides commercial terms.
