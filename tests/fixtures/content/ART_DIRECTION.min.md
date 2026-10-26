# Art direction (synthetic excerpt for tests; same table and template format as art/ART_DIRECTION.md)

## (a) Avatar system spec

8. **Codex pass:** 4 candidates; STANDARD §9.1 seeds (CompleteTech 1025, AI-Ascension 2401, Jev-Engineering 3001, jevplay-games 3101).

## (b) Family palette

| Family | Role | Name | Hex | Notes |
|---|---|---|---|---|
| **Shared (all 28)** | Tile centre | Night Core | `#1C2333` | radial centre |
| **CompleteTech core** (17 orgs) | Line | Signal Blue | `#46B8FF` | core `#CBEBFF`; 7.1:1 |
| | Glow | Cloud Blue | `#0081ED` | the logo's gradient mid-stop |
| | Spark | Bulb Gold | `#FFC300` | centre `#FFF0BF`, bloom `#FFA800`; 9.8:1 |
| | Light-surface ink / spark | Royal / Deep Gold | `#005ADD` / `#A87C00` | 5.6:1 / 3.6:1 |
| **Jev** (3 orgs) | Jev-Engineering line | Jev Violet | `#B79DFF` | core `#EBE4FF`, glow `#7C3AED`; 6.9:1 |
| | Jev-Engineering spark | Hub White | `#E8FDFF` | centre `#FFFFFF`, bloom `#22D3EE` |
| | jevplay-games line | Jev Pink | `#FF8FA3` | core `#FFE0E5`, glow `#E551BA` |
| | jevplay-games spark | Jev Cyan | `#32D3EE` | centre `#CCF4FB`, bloom `#06B6D4` |
| | Light-surface inks | Violet / Teal / Rose | `#684EB0` / `#0E7490` / `#B4235F` | |

## (c) All 28 accounts

| # | Account | Family | Hue | Spark | Glyph | Keeps existing mark |
|---|---|---|---|---|---|---|
| 1 | Northwind-Trading-Co | CompleteTech core | `#46B8FF` | `#FFC300` | Compass rose; spark is the north point (SQUARE) | No |

## (d) Shared prompt template

```text
NEON NIGHT AVATAR · STYLE LOCK v1.2 · {ACCOUNT}

Create one square 1024 × 1024 px image: the GitHub avatar for the {KIND} "{ACCOUNT}". It is one of 28 avatars in a single matched family. The pipeline downsamples your image to the 500 × 500 px PNG that is uploaded.

1 FORMAT. GitHub crops the image itself ({CROP}).

2 BACKGROUND (identical in all 28 avatars). On it, {POOL}.

4 LIGHT. Bloom {GLOW_HEX}; glow {LINE_HEX}; core {CORE_HEX}.{SECONDARY_LIGHT}

5 THE SPARK. One circle, {SPARK_D} px, in {SPARK_NAME} {SPARK_HEX}, centre {SPARK_CORE_D} px in {SPARK_CORE_HEX}, bloom {SPARK_BLOOM_HEX}. It is the only filled shape in the image{SPARK_EXCLUSIVITY}. Placement: {SPARK_PLACEMENT}

6 COMPOSITION. Inside the central 688 × 688 px square{CIRCLE_CLAUSE}. Size class {SIZE_CLASS}.

7 THE GLYPH: {GLYPH_NAME}. {GLYPH_DESCRIPTION}

8 COLOURS. Line {LINE_NAME} {LINE_HEX}{SECONDARY_LINE}; spark {SPARK_NAME} {SPARK_HEX}.

9 NEVER. {TEXT_RULE}; borders. {EXTRA_NEGATIVES}

10 REFERENCES (attach as input images). (a) Geometry: art/reference/avatars/{ACCOUNT}.png, the system compositor's render of this exact glyph. Match it exactly; your job is flawless rendering, not redesign. (b) Style: {STYLE_REFERENCES} (c) {BRAND_REFERENCE}

Run settings, not part of the image: same model and version for all 28; 4 candidates; seed {SEED} if the tool supports seeds; output art/out/avatars/{ACCOUNT}-1024-c{1..4}.png.
```

## (e) Codex-ready prompts
