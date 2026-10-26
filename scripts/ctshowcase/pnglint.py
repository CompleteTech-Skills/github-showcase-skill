"""PNG integrity (the exemplar's validate_png) and the README banner checks (spec A6.11 `lint banner`)."""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

BANNER_SIZES = ((1280, 360), (2560, 720))
BANNER_BUDGET = 300_000
MIN_CHIPS = 2  # decision 13: two to four fact chips; fewer is incomplete, never pass


def validate_png(data: bytes) -> tuple[int, int, int]:
    """Check bounded chunks and CRCs; return (width, height, colour type). Raises ValueError."""
    if len(data) > 16 * 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid or oversized PNG")
    offset, header, image, dims = 8, False, False, None
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + length + 12
        if end > len(data):
            raise ValueError("truncated PNG chunk")
        payload = data[offset + 8:end - 4]
        if zlib.crc32(kind + payload) != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("PNG checksum mismatch")
        if not header and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if kind == b"IHDR":
            if header or length != 13:
                raise ValueError("invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if not 0 < width < 2**31 or not 0 < height < 2**31 or depth not in depths.get(color, ()) or compression \
                    or filtering or interlace not in (0, 1):
                raise ValueError("invalid PNG parameters")
            header, dims = True, (width, height, color)
        elif kind == b"IDAT":
            image = image or bool(length)
        elif kind == b"IEND":
            if length or not image or end != len(data):
                raise ValueError("invalid PNG end")
            return dims
        offset = end
    raise ValueError("incomplete PNG")


def chunk_types(data: bytes) -> list[str]:
    out, off = [], 8
    while off + 12 <= len(data):
        n = struct.unpack_from(">I", data, off)[0]
        out.append(data[off + 4:off + 8].decode("latin-1"))
        off += n + 12
    return out


def lint_banner(path: str | Path) -> dict:
    p = Path(path)
    fails, warns, incomplete = [], [], []
    if not p.is_file():
        return {"file": str(p), "result": "FAIL", "fails": ["missing"], "warns": []}
    data = p.read_bytes()
    try:
        w, h, color = validate_png(data)
    except ValueError as exc:
        return {"file": str(p), "result": "FAIL", "fails": [f"png: {exc}"], "warns": [], "bytes": len(data)}
    opaque = color in (0, 2) or (color == 3 and "tRNS" not in chunk_types(data))
    if not opaque:
        fails.append("banner must be opaque RGB (no alpha)")
    if (w, h) not in BANNER_SIZES:
        fails.append(f"size {w}x{h} not 1280x360 or 2560x720")
    if len(data) > BANNER_BUDGET:
        fails.append(f"bytes {len(data)} > {BANNER_BUDGET}")
    side = p.parent / ".showcase.json"
    if side.is_file():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
            rec = (meta.get("outputs") or {}).get(p.name)
            if rec and rec.get("sha256") != hashlib.sha256(data).hexdigest():
                fails.append("sidecar sha256 does not match the file (hand-edited or stale)")
            elif not rec:
                warns.append("sidecar has no record for this file")
            elif isinstance(rec.get("chips"), list) and len(rec["chips"]) < MIN_CHIPS:
                incomplete.append("needs-input:banner-chips")
        except ValueError:
            fails.append("sidecar is not valid JSON")
    else:
        warns.append("no .showcase.json sidecar")
    result = "FAIL" if fails else "INCOMPLETE" if incomplete else "PASS"
    return {"file": str(p), "result": result, "fails": fails, "warns": warns, "logs": incomplete, "bytes": len(data),
            "px": [w, h]}
