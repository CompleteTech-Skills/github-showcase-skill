# Brand identity and legal wording

An organization's family supplies its visual identity. A co-owner's permission to
run a command does not supply a missing palette or mark. The TicketStub family is
marked `identity_pending: true`: its generators return `needs-input:brand-identity`
until owner-supplied identity data is configured, even with `--allow-unmeasured`.
Without T3 sign-off, the existing consent refusal still takes precedence.

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
