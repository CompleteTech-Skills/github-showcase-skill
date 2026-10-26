"""Minimal JSON Schema (draft 2020-12 subset) validator, stdlib only.

Supports: type, enum, const, pattern, minLength, maxLength, minimum, maximum, properties, required,
additionalProperties, patternProperties, items, minItems, maxItems, uniqueItems, anyOf, $ref (#/$defs/...).
"""
from __future__ import annotations

import re

_TYPES = {
    "string": str, "object": dict, "array": list, "boolean": bool, "null": type(None),
}


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def validate(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = root if root is not None else schema
    errors: list[str] = []
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            return [f"{path}: unsupported $ref {ref}"]
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return validate(value, target, root, path)
    if "anyOf" in schema:
        if all(validate(value, s, root, path) for s in schema["anyOf"]):
            errors.append(f"{path}: matches no anyOf branch")
    t = schema.get("type")
    if t is not None:
        names = t if isinstance(t, list) else [t]
        if not any(_is_type(value, n) for n in names):
            return errors + [f"{path}: expected {'/'.join(names)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 30):
            errors.append(f"{path}: length out of range")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        pattern_props = schema.get("patternProperties", {})
        for key, item in value.items():
            sub = f"{path}.{key}"
            if key in props:
                errors += validate(item, props[key], root, sub)
                continue
            matched = False
            for pat, s in pattern_props.items():
                if re.search(pat, key):
                    matched = True
                    errors += validate(item, s, root, sub)
            if matched:
                continue
            extra = schema.get("additionalProperties", True)
            if extra is False:
                errors.append(f"{path}: key {key!r} is not allowed")
            elif isinstance(extra, dict):
                errors += validate(item, extra, root, sub)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1 << 30):
            errors.append(f"{path}: item count out of range")
        if schema.get("uniqueItems") and len({repr(v) for v in value}) != len(value):
            errors.append(f"{path}: items must be unique")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")
    return errors
