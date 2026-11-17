# Staged descriptions

Pass `--description "A reviewed sentence."` to `banner`, `card`, `content social`
or `readme` to render from that proposal without changing the captured metadata
file or GitHub's About text. The hidden `social-preview` alias accepts the same
option. An empty or multiline value returns `needs-input:description`.

The command reports `staged-description` and the proposed text, its SHA-256 and
the captured live description's SHA-256. It uses the proposal for type detection
and as the description input to the renderer. For banners, an explicit or
configured subtitle takes precedence. Follow the normal description check and
the orchestrator's writer queue to approve the sentence for publication.

Each staged artifact has its own `staged_description` record in
`docs/images/.showcase.json`. Records for other outputs are retained, so rendering
only the card does not claim the banner was refreshed. For explicit output paths
outside the target checkout, the sidecar is placed beside that output; metadata-only
rendering uses that location too. README dry runs report the proposal without
writing a sidecar. `readme --write` records the proposal when the resulting
README has a managed tagline with that text, including an already-current tagline.
`content social --job` requires rendering from captured metadata.
An ordinary render replaces the record for each refreshed output with its current
hash and no staged description, while leaving untouched output records intact.
Card PNG previews have their own records. Banner and card records retain the
captured repository ID when available. The sidecar's top-level inputs and
fingerprint describe the most recent recorded output. Before skipping generation,
the Action checks the selected banner and card for current records in a sidecar
with per-output fingerprints. It also checks any existing README record when
README refresh is enabled. Older sidecars use the top-level fingerprint.
A selected art surface with no record is rechecked on the next run, including
a surface whose renderer reports an exemption.

`doctor` compares each managed tagline block with what `readme` would write for the
live description in the supplied metadata (`readme.tagline_body`, the one place that
decides the tagline format, in any variant's form). A mismatch fails R2 and logs
`description-drift:readme`, even if the live sentence also appears somewhere else in
the document. Code examples are ignored. This is a local comparison, so capture
current metadata before relying on it. The existing R7 check still handles an absent
or unmanaged tagline.

When the live description is empty, `readme` preserves an authored tagline and
logs `needs-input:description`. `doctor` still reports drift if the current
README matches the staged artifact hash and its managed tagline carries that
proposal. Upgrades for variants G (fork) and H (archive) write a callout.
`doctor` also checks any managed tagline those upgrades preserve.
