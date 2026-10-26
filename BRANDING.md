# CompleteTech LLC Skills: branding and handoffs

[Start here](ONBOARDING.md) · [Asset rights](BRAND_ASSETS.md) · [Specialist instructions](SKILL.md)

## Resolve identity before rendering

This skill renders the identity of the organization that owns the repository, never a guess. The owner's row in `references/brand.yaml` selects the brand family (CompleteTech, AI Ascension, Jev Engineering, jevplay.games, LibreEvolve, Touched By An Agent or romgenie), its company label, eyebrow and palette. Excluded, hold and T3 owners are refused. Preserve the operator's explicit settings; ask about unresolved identity instead of applying CompleteTech branding to a business outside the estate. The only outside name the examples use is the fictional demo client, Northwind Trading Co.

T2 families keep their own look: AI-Ascension keeps its existing banners, TouchedByAnAgent is on hold until the user decides whether it mentions CompleteTech, and T3 orgs (Pick-Your-AI, Jevelopers-neatHack-2026) get nothing until their co-owners sign off. CompleteTech examples identify this library, not permission to represent another business.

Use only the committed brand files in `assets/brand/` and the per-org marks in `assets/orgs/`. Do not synthesize replacement marks, fetch remote artwork, crop, mask or recolour a mark, redistribute fonts outside their OFL terms, or transfer private seals or signatures to public repositories. The MIT code license does not replace the asset policy.

## Palette and type

The palette, fonts and logo paths are data, kept in one place: [`references/brand.yaml`](references/brand.yaml). Generators read nothing else, and the quality gate rejects colour literals in `scripts/`. [references/art-direction.md](references/art-direction.md) documents each family's palette and motif for people and image prompts; when the two disagree, `brand.yaml` is what renders.

The estate uses one dark design per surface on both GitHub themes (decision 21). The navy grid plate reads on white pages too, as the php2shell-check banner shows. The decision 18 footer is the one place a light and a dark logo are swapped with `<picture>`, because the logo itself must stay visible on both themes.

Typography: Poppins (eyebrows, subtitles, chips) and JetBrains Mono (slugs) for CompleteTech; Fraunces and Bricolage Grotesque for AI Ascension; Press Start 2P only at 36 px or larger for jevplay.games. All text is outlined to paths at build time.

## Handoff to the next skill

Carry verified facts and their sources, artifact path/version, approved identity and local logo path, palette overrides, confidentiality, intended audience, approval owner/status, blockers and next specialist. Preserve these in the orchestrator's existing `project_state`; do not replace its workflow schema with an incompatible parallel state format. For estate work, also carry the `logs[]` codes and any change records the commands emitted, unchanged.

Missing approval stays unknown or draft. Rendering, a passing lint, a clean package check or a reused brand does not authorize a GitHub write, publication, visibility change or launch. Review the actual output for clipping, contrast, placeholders and factual accuracy before approved use, and judge art as a set on a contact sheet.
