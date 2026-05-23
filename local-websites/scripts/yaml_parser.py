#!/usr/bin/env python3
"""
Minimal YAML parser — handles the subset of YAML used by our config files.
Supports: scalars, nested mappings, sequences (lists), comments (#).
No anchors, aliases, tags, multi-line scalars, or flow style.
"""

def parse_yaml(text: str) -> dict:
    """Parse a simple YAML document into a Python dict."""
    lines = text.split("\n")
    root = {}
    _parse_block(lines, 0, root, 0, len(lines))
    return root


def _parse_block(lines: list[str], idx: int, target: dict | list,
                  base_indent: int, end: int) -> int:
    """Parse a block of YAML at a given indentation level into target.
    Returns the next line index after this block."""
    if idx >= end:
        return idx

    # Determine if this block is a sequence (list) or mapping (dict)
    is_sequence = isinstance(target, list)

    while idx < end:
        line = lines[idx]

        # Skip empty lines and full-line comments
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        # Calculate indentation
        indent = len(line) - len(line.lstrip())
        if indent < base_indent:
            # Less indented — this block is done
            return idx

        content = stripped

        if is_sequence:
            # Sequence item: must start with "- "
            if content.startswith("- "):
                value_str = content[2:].strip()
                # Check if value is a mapping (no scalar — next line is more indented)
                if idx + 1 < end:
                    next_line = lines[idx + 1]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    next_stripped = next_line.strip()
                    if (next_indent > indent and next_stripped
                            and not next_stripped.startswith("#")
                            and not next_stripped.startswith("- ")):
                        # Nested mapping
                        mapping = {}
                        idx = _parse_block(lines, idx + 1, mapping, indent + 2, end)
                        target.append(mapping)
                        continue
                # Scalar value or empty
                target.append(_parse_scalar(value_str) if value_str else {})
                idx += 1
            else:
                # Not a list item any more — this block done
                return idx
        else:
            # Mapping: expect "key:" or "key: value"
            if ":" in content:
                # Split on first colon, respecting inline values
                colon_idx = content.index(":")
                key = content[:colon_idx].strip()
                value_str = content[colon_idx + 1:].strip()

                if value_str:
                    # Inline scalar value
                    target[key] = _parse_scalar(value_str)
                    idx += 1
                else:
                    # Value is on following lines (block)
                    # Peek ahead to determine type
                    if idx + 1 < end:
                        next_line = lines[idx + 1]
                        next_indent = len(next_line) - len(next_line.lstrip())
                        next_stripped = next_line.strip()
                        if not next_stripped or next_stripped.startswith("#"):
                            # Empty value
                            target[key] = None
                            idx += 1
                        elif next_stripped.startswith("- ") and next_indent > indent:
                            # Sequence
                            seq = []
                            idx = _parse_block(lines, idx + 1, seq, indent + 2, end)
                            target[key] = seq
                        elif next_indent > indent:
                            # Nested mapping
                            mapping = {}
                            idx = _parse_block(lines, idx + 1, mapping, indent + 2, end)
                            target[key] = mapping
                        else:
                            # Same or less indent — null value
                            target[key] = None
                            idx += 1
                    else:
                        target[key] = None
                        idx += 1
            else:
                # Not a valid mapping line — skip
                idx += 1

    return idx


def _parse_scalar(value: str):
    """Parse a scalar YAML value into its Python type."""
    value = value.strip()
    # Remove trailing comments (but not inside quotes)
    if "#" in value and '"' not in value and "'" not in value:
        # Simple heuristic: split on # only if preceded by space
        parts = value.split(" #", 1)
        value = parts[0].strip()

    # Remove quotes
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Booleans
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Null
    if value.lower() in ("null", "~", ""):
        return None

    # Numbers
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def load_yaml_file(path: str) -> dict:
    """Load and parse a YAML file."""
    with open(path) as f:
        return parse_yaml(f.read())


# Replace the PyYAML import
def _patch_generator():
    """Patch generate.py to use our parser instead of PyYAML."""
    import os
    gen_path = os.path.join(os.path.dirname(__file__),
                            "..", "scripts", "generate.py")
    # We'll handle this differently — just make parse_yaml available
