# Synthetic legacy art direction

This is a synthetic test fixture that imitates the pre-#61 template syntax: it asked for four candidates and used a seed placeholder. It contains no production brand data. The original lives in git history (commits baa3c02 and 71ffd4a).

## Repository glyph prompt template

```text
SYNTHETIC LEGACY REPO ICON · {ACCOUNT}

Create one square 1024 × 1024 px image of a single repository glyph.
Keep the background empty and the glyph inside the central 688 × 688 px square.
Size class {SIZE_CLASS}.

GLYPH: {GLYPH_NAME}. {GLYPH_DESCRIPTION}
SPARK PLACEMENT: {SPARK_PLACEMENT}
PALETTE: outline {LINE_HEX}, glow {GLOW_HEX}; one spark in {SPARK_HEX}.

No text, letters, numbers, words, logos, brand marks, human figures or third-party IP.
{EXTRA_NEGATIVES}

Produce four candidates. {SEED_INSTRUCTION}
```

## Prompt template for illustrations

```text
[STYLE LOCK — FAMILY]
FAMILY STYLE LOCK, VERBATIM

[SUBJECT]
One sentence: the single hero object or scene that represents the repository or org's function.

[OBJECTS]
3–5 objects. Only objects from a synthetic placeholder library.

[COMPOSITION]
Isolated platform and objects on a perfectly flat, untextured BG background; 10% empty margin on all sides. Square 1024x1024 | Wide 1536x1024.

[PALETTE]
Use only these colors: PALETTE. HIGHLIGHT LINE

[EXCLUSIONS]
No text, letters, numbers, symbols, words, labels, logos or brand marks. FAMILY ADDITIONS
```

| Family | Style lock (verbatim) |
|---|---|
| completetech | Synthetic placeholder style lock: flat neutral shapes on a plain ground. |

- Family additions: none (synthetic fixture).
