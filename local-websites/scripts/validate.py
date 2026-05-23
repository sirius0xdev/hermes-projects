#!/usr/bin/env python3
"""Validate all generated manifests have valid YAML syntax."""
import sys
sys.path.insert(0, "scripts")
from yaml_parser import parse_yaml
from pathlib import Path

overlays = Path("overlays")
errors = []
for site_dir in sorted(overlays.iterdir()):
    if not site_dir.is_dir():
        continue
    for manifest in sorted(site_dir.glob("*.yaml")):
        try:
            with open(manifest) as f:
                content = f.read()
            parsed = parse_yaml(content)
            if parsed is None:
                errors.append(f"{manifest.name}: parsed to None")
        except Exception as e:
            errors.append(f"{manifest.name}: {e}")

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
else:
    manifests = list(Path("overlays").rglob("*.yaml"))
    print(f"✅ All {len(manifests)} YAML manifests valid")
