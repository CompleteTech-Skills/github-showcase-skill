# Organization marks

Per-organization marks for the icon card, one folder per owner: `assets/orgs/OWNER/mark.png`. The path for each org is its `mark` entry in `references/brand.yaml`.

Every T1 organization except CompleteTech-LLC carries its **Neon Night** avatar here (the approved avatar system, `art/ART_DIRECTION.md` v1.2): the 500 px compositor render from `art/reference/avatars/<Org>.png`, copied byte for byte. CompleteTech-LLC repositories keep the full CompleteTech logo on the white card (the golden look). Replace a file with the final 1024 px render once the avatar is uploaded; nothing in `scripts/` changes.

A Neon Night avatar brings its own night tile (`#171E28` corners), so the banner card and the card tile take that ground and draw the avatar full-bleed with the family accent edge: there is never a plate inside a plate. T2 families have no folder yet; until their marks are approved they show their typeset wordmark on the family's dark plate (a T2 card never carries the CompleteTech logo).

A mark here is a fallback only: every in-scope repository gets its own `assets/icon.png` (decision 12), which always takes precedence and logs nothing; a mark logs `needs-input:repo-icon`. Marks are placed unaltered, never cropped or recoloured by the generators, and they are CompleteTech LLC brand assets reserved under [BRAND_ASSETS.md](../../BRAND_ASSETS.md).

| Requirement | Value |
|---|---|
| Format | PNG; either transparent, or with one opaque square ground (all four corners within ΔE 3), which then fills the card |
| Size | 500 px or more on the long side (the banner never upscales a mark beyond 2× its pixels); at most 300 KB |
| Content | The org's mark only; no wordmark text |
