#!/usr/bin/env python3
"""
Auto-Provisioning Deploy Script

One command: config file → generated site → deployed to GKE cluster.

Usage:
    # Deploy a single site
    python scripts/deploy.py configs/example-landscaping.yaml

    # Deploy all configs
    python scripts/deploy.py --all

    # Dry-run (generate + validate, don't apply)
    python scripts/deploy.py configs/landscaping.yaml --dry-run

    # Delete a site
    python scripts/deploy.py --delete landscaping-business

Pre-requisites:
    - kubectl configured for the target GKE cluster
    - Gateway "external-http-gateway" already provisioned in customer1 namespace
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Import the generator
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from generate import generate, OVERLAYS_DIR


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = PROJECT_ROOT / "configs"


def run(cmd: list[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command, or print it in dry-run mode."""
    cmd_str = " ".join(cmd)
    if dry_run:
        print(f"   [dry-run] {cmd_str}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    print(f"   $ {cmd_str}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Failed (exit {result.returncode})")
        if result.stderr.strip():
            print(f"   stderr: {result.stderr.strip()[-500:]}")
        if result.stdout.strip():
            print(f"   stdout: {result.stdout.strip()[-500:]}")
    return result


def check_prerequisites() -> bool:
    """Verify kubectl is available and Gateway exists."""
    # Check kubectl
    result = subprocess.run(["kubectl", "version", "--client", "--short"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ kubectl not found or not configured.")
        return False
    print(f"✅ kubectl: {result.stdout.strip()}")

    # Check cluster connectivity
    result = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ Cannot connect to cluster.")
        print(f"   {result.stderr.strip()}")
        return False
    print("✅ Cluster reachable")

    # Check Gateway exists
    result = subprocess.run(
        ["kubectl", "get", "gateway", "external-http-gateway", "-n", "customer1",
         "-o", "jsonpath={.metadata.name}"],
        capture_output=True, text=True)
    if result.stdout.strip() != "external-http-gateway":
        print("⚠️  Gateway 'external-http-gateway' not found in customer1 namespace.")
        print("   HTTPRoutes will fail to bind. Deploy the Gateway first.")
        # Don't fail — gateway might exist in a different namespace or be deploying
    else:
        print("✅ Gateway 'external-http-gateway' found")

    return True


def deploy_site(config_path: str, dry_run: bool = False) -> bool:
    """Generate and deploy a single site.

    Returns True on success.
    """
    # Step 1: Generate
    print(f"\n── Step 1: Generate manifests ──")
    result = generate(config_path)
    out_dir = Path(result["out_dir"])
    site_name = result["site_name"]

    # Step 2: Apply with kustomize
    print(f"\n── Step 2: Apply to cluster ──")
    cmd = ["kubectl", "apply", "-k", str(out_dir)]
    proc = run(cmd, dry_run=dry_run)
    if proc.returncode != 0 and not dry_run:
        print(f"❌ Deploy failed for {site_name}")
        return False

    # Step 3: Wait for rollout
    if not dry_run:
        print(f"\n── Step 3: Wait for rollout ──")
        wait_cmd = ["kubectl", "rollout", "status", f"deployment/{site_name}",
                     "-n", result["namespace"], "--timeout=120s"]
        run(wait_cmd, dry_run=False)

        # Step 4: Quick health check
        print(f"\n── Step 4: Verify ──")
        run(["kubectl", "get", "pods", "-n", result["namespace"], "-l", f"app={site_name}"],
            dry_run=False)
        run(["kubectl", "get", "httproute", "-n", result["namespace"]], dry_run=False)

    print(f"\n✅ Site deployed: https://{result['domain']}")
    return True


def delete_site(site_name: str, dry_run: bool = False) -> bool:
    """Delete an entire site (namespace and all resources)."""
    overlay_dir = OVERLAYS_DIR / site_name
    if not overlay_dir.exists():
        print(f"❌ Overlay not found: {overlay_dir}")
        print(f"   Available overlays: {[d.name for d in OVERLAYS_DIR.iterdir() if d.is_dir()]}")
        return False

    print(f"\n── Deleting site: {site_name} ──")

    # Check if namespace exists
    ns_check = subprocess.run(
        ["kubectl", "get", "namespace", site_name, "-o", "name"],
        capture_output=True, text=True)
    namespace_exists = ns_check.returncode == 0

    if namespace_exists:
        # Delete via kustomize (handles cleanup ordering)
        cmd = ["kubectl", "delete", "-k", str(overlay_dir)]
        run(cmd, dry_run=dry_run)

        # Also clean up the overlay dir
        if not dry_run:
            print(f"\n── Cleaning up generated files ──")
            shutil.rmtree(overlay_dir)
    else:
        print(f"   Namespace '{site_name}' not found on cluster — cleaning up local files only.")
        if not dry_run:
            shutil.rmtree(overlay_dir)

    print(f"✅ Site '{site_name}' deleted.")
    return True


def deploy_all(dry_run: bool = False) -> int:
    """Deploy all configs in the configs/ directory.

    Returns count of successful deploys.
    """
    configs = sorted(CONFIGS_DIR.glob("*.yaml"))
    if not configs:
        print("❌ No config files found in configs/")
        return 0

    print(f"Found {len(configs)} config(s)")
    success = 0
    for cfg in configs:
        try:
            if deploy_site(str(cfg), dry_run=dry_run):
                success += 1
        except Exception as e:
            print(f"❌ Failed to deploy {cfg.name}: {e}")

    print(f"\n{'─'*50}")
    print(f"Deployed: {success}/{len(configs)}")
    return success


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    # Pre-check
    if not check_prerequisites():
        sys.exit(1)

    arg = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if arg == "--delete":
        if len(sys.argv) < 3:
            print("Usage: python scripts/deploy.py --delete <site-name>")
            sys.exit(1)
        delete_site(sys.argv[2], dry_run)
    elif arg == "--all":
        deploy_all(dry_run)
    elif arg == "--list":
        overlays = [d.name for d in OVERLAYS_DIR.iterdir() if d.is_dir()]
        print(f"Generated overlays ({len(overlays)}):")
        for o in sorted(overlays):
            print(f"  - {o}")
    else:
        config_path = Path(arg)
        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            print(f"   Try: python scripts/deploy.py configs/example-landscaping.yaml")
            sys.exit(1)
        deploy_site(str(config_path), dry_run)


if __name__ == "__main__":
    main()
