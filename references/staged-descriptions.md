# Staged descriptions

Pass `--description "A reviewed sentence."` to `banner`, `card`, `content social`
or `readme` to render from that proposal without changing the captured metadata
file or GitHub's About text. The hidden `social-preview` alias accepts the same
option. An empty or multiline value returns `needs-input:description`.

The command reports `staged-description` and the proposed text, its SHA-256 and
the captured live description's SHA-256. It uses the proposal for type detection
and for the rendered description. This does not approve the sentence for
publication: run the normal description check and submit the proposal to the
orchestrator's writer queue.

Each successfully written output has its own `staged_description` record in
`docs/images/.showcase.json`. Records for other outputs are retained, so rendering
only the card does not claim the banner was refreshed. For explicit output paths
outside the target checkout, the sidecar is placed beside that output; metadata-only
rendering uses that location too. README dry runs report the proposal without
writing a sidecar; `readme --write` records it even if the README is already current.
An ordinary render replaces the record for each refreshed output with its current
hash and no staged description, while leaving untouched output records intact.
Card PNG previews have their own records. Banner and card records retain the
captured repository ID when available. The sidecar's top-level inputs and
fingerprint describe the most recent recorded output, not every retained record.

`doctor` compares the rendered managed tagline with the live description in the
supplied metadata. A mismatch fails R2 and logs `description-drift:readme`, even if
the live sentence also appears somewhere else in the document. Code examples are
ignored. This is a local comparison, so capture current metadata before relying
on it. The existing R7 check still handles an absent or unmanaged tagline.
