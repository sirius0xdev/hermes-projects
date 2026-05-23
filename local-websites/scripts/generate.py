#!/usr/bin/env python3
"""
Local Business Website Generator

Takes a YAML config file and produces:
  1. Static HTML site with inline CSS
  2. Kubernetes manifests (Namespace, ConfigMaps, Deployment, Service, HealthCheckPolicy)
  3. Gateway API HTTPRoute for subdomain routing
  4. Kustomization to tie everything together

Usage:
    python scripts/generate.py configs/landscaping-business.yaml

Output lands in: overlays/<business-name>/

Design decisions:
  - Single-file HTML (no external assets) → one ConfigMap, zero image builds
  - nginx:alpine as the static server (3 MB, fast)
  - Gateway API HTTPRoute tied to "external-http-gateway" (GKE L7 global external)
  - ConfigMap limits: 1 MiB max (well over our ~8 KB sites). If exceeded,
    the script switches to hostPath + initContainer mode automatically.
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

# Use our minimal YAML parser (no PyYAML dependency)
from yaml_parser import parse_yaml as yaml_load


# ── Paths ────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates" / "site-template"
OVERLAYS_DIR = PROJECT_ROOT / "overlays"
K8S_BASE_DIR  = PROJECT_ROOT / "k8s" / "base" / "static-site"

# ConfigMap size limit (GKE default)
CONFIGMAP_MAX_BYTES = 1_000_000  # ~1 MiB


# ═══════════════════════════════════════════════════════════════════════════════════════
# HTML Generation
# ═══════════════════════════════════════════════════════════════════════════════════════

def render_services_section(section: dict) -> str:
    """Render a services grid section."""
    items_html = ""
    for item in section.get("items", []):
        items_html += f"""            <div class="service-card">
                <div class="icon">{item["icon"]}</div>
                <h3>{item["title"]}</h3>
                <p>{item["description"]}</p>
            </div>
"""
    title_html = f'<h2 class="section-title">{section.get("title", "Services")}</h2>'
    return f"""    <section>
        {title_html}
        <div class="services-grid">
{items_html}        </div>
    </section>"""


def render_about_section(section: dict) -> str:
    """Render an about section."""
    title = section.get("title", "About Us")
    content = section["content"]
    return f"""    <section>
        <h2 class="section-title">{title}</h2>
        <div class="about-content">
            <p>{content}</p>
        </div>
    </section>"""


def render_contact_section(section: dict, config: dict) -> str:
    """Render a contact section with optional phone, email, address, hours."""
    biz = config["business"]
    title = section.get("title", "Contact Us")
    items_html = ""

    if section.get("show_phone"):
        items_html += f"""            <div class="contact-item">
                <div class="label">Phone</div>
                <div class="value">{biz["phone"]}</div>
            </div>
"""
    if section.get("show_email"):
        items_html += f"""            <div class="contact-item">
                <div class="label">Email</div>
                <div class="value"><a href="mailto:{biz["email"]}" style="color:var(--primary)">{biz["email"]}</a></div>
            </div>
"""
    if section.get("show_address"):
        items_html += f"""            <div class="contact-item">
                <div class="label">Address</div>
                <div class="value">{biz["address"]}</div>
            </div>
"""
    has_hours = section.get("show_hours") and section.get("hours")
    return f"""    <section>
        <h2 class="section-title">{title}</h2>
        <div class="contact-grid">
{items_html}        </div>
{"        " + render_hours(section) if has_hours else ""}
    </section>"""


def render_hours(section: dict) -> str:
    """Render business hours table."""
    hours = section["hours"]
    # Ordered days
    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    rows = ""
    for d in days:
        if d in hours:
            rows += f"""            <tr><td class="day">{d.capitalize()}</td><td class="time">{hours[d]}</td></tr>
"""
    return f"""<table class="hours-table" style="margin-top:2rem">
{rows}        </table>"""


def render_section(section: dict, config: dict) -> str:
    """Dispatch to the correct section renderer."""
    t = section.get("type")
    if t == "services":
        return render_services_section(section)
    elif t == "about":
        return render_about_section(section)
    elif t == "contact":
        return render_contact_section(section, config)
    else:
        return f"    <!-- Unknown section type: {t} -->"


def build_html(config: dict) -> str:
    """Generate the full static HTML from config."""
    biz = config["business"]
    home = config["pages"]["home"]

    # Build nav links from section titles
    sections = home.get("sections", [])
    nav_links = ""
    for s in sections:
        title = s.get("title", s.get("type", "").capitalize())
        nav_links += f'<li><a href="#{s.get("type")}">{title}</a></li>\n            '

    if not nav_links.strip():
        nav_links = '<li><a href="#contact">Contact</a></li>'

    # Build section HTML
    section_html = ""
    for s in sections:
        section_html += render_section(s, config) + "\n\n"

    # Read template
    template_path = TEMPLATE_DIR / "index.html"
    with open(template_path) as f:
        template = Template(f.read())

    return template.safe_substitute(
        TITLE=biz["title"],
        TAGLINE=biz["tagline"],
        PRIMARY_COLOR=biz["colors"]["primary"],
        SECONDARY_COLOR=biz["colors"]["secondary"],
        ACCENT_COLOR=biz["colors"]["accent"],
        TEXT_COLOR=biz["colors"]["text"],
        LOGO_TEXT=biz["logo_text"],
        PHONE=biz["phone"],
        ADDRESS=biz["address"],
        NAV_LINKS=nav_links.strip(),
        HERO_HEADLINE=home["hero"]["headline"],
        HERO_SUBHEADLINE=home["hero"]["subheadline"],
        HERO_CTA=home["hero"]["cta"],
        SECTIONS=section_html.strip(),
        CURRENT_YEAR=str(datetime.now().year),
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# Kubernetes Manifest Generation
# ═══════════════════════════════════════════════════════════════════════════════════════

def load_k8s_template(name: str) -> str:
    """Load a base K8s template from the static-site base directory."""
    path = K8S_BASE_DIR / f"{name}.yaml"
    with open(path) as f:
        return f.read()


def render_k8s_deployment(site_name: str, namespace: str) -> str:
    """Render a site-specific Deployment from the base template."""
    template = load_k8s_template("deployment")
    return template.replace("SITE_NAMESPACE", namespace).replace("SITE_NAME", site_name)


def render_k8s_service(site_name: str, namespace: str) -> str:
    """Render a site-specific Service."""
    template = load_k8s_template("service")
    return template.replace("SITE_NAMESPACE", namespace).replace("SITE_NAME", site_name)


def render_k8s_healthcheck(site_name: str, namespace: str) -> str:
    """Render a site-specific HealthCheckPolicy."""
    template = load_k8s_template("healthcheck")
    return template.replace("SITE_NAMESPACE", namespace).replace("SITE_NAME", site_name)


def render_content_configmap(site_name: str, namespace: str, html_content: str) -> str:
    """Render a ConfigMap with the site HTML content."""
    # YAML-safe: use a literal block scalar for the HTML
    # Escape any triple-hyphens that might break YAML document separation
    safe_html = html_content.replace("---", "\\u002D\\u002D\\u002D")
    return f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {site_name}-content
  namespace: {namespace}
data:
  index.html: |
    {safe_html}
"""


def render_nginx_configmap(site_name: str, namespace: str, domain: str) -> str:
    """Render a ConfigMap with nginx config."""
    return f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {site_name}-nginx-config
  namespace: {namespace}
data:
  default.conf: |
    server {{
        listen 80;
        server_name {domain} *.{domain};
        root /usr/share/nginx/html;
        index index.html;

        location / {{
            try_files $uri $uri/ =404;
        }}

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # Gzip
        gzip on;
        gzip_types text/html text/css application/javascript;
        gzip_min_length 256;
    }}
"""


def render_namespace(namespace: str) -> str:
    return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
"""


def render_httproute(site_name: str, namespace: str, domain: str, gateway_namespace: str = "customer1") -> str:
    """Render a Gateway API HTTPRoute for the site's subdomain.

    The Gateway lives in customer1 namespace (existing infrastructure).
    HTTPRoutes can reference Gateways across namespaces (allowedRoutes.from: All).
    """
    return f"""apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {site_name}-route
  namespace: {namespace}
spec:
  parentRefs:
  - name: external-http-gateway
    namespace: {gateway_namespace}
  hostnames:
  - "{domain}"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: {site_name}-svc
      port: 80
"""


def render_kustomization(site_name: str, namespace: str, resources: list[str]) -> str:
    """Render a kustomization.yaml for the site overlay."""
    resource_lines = "\n".join(f"  - {r}" for r in resources)
    return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: {namespace}
resources:
{resource_lines}
"""


# ═══════════════════════════════════════════════════════════════════════════════════════
# File Output
# ═══════════════════════════════════════════════════════════════════════════════════════

def write_manifest(path: Path, content: str):
    """Write a manifest file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def generate(config_path: str) -> dict:
    """Main entry point: config file → output directory full of manifests + HTML.

    Returns a dict with paths and metadata for the deploy script.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml_load(f.read())

    biz = config["business"]
    site_name = biz["name"]
    namespace = biz.get("namespace", site_name)
    domain = f"{site_name}.{biz['domain_base']}"

    print(f"🏗️  Generating site: {biz['title']}")
    print(f"   Domain:    {domain}")
    print(f"   Namespace: {namespace}")
    print(f"   Colors:    primary={biz['colors']['primary']} accent={biz['colors']['accent']}")

    # 1. Generate HTML
    html = build_html(config)
    html_size = len(html.encode("utf-8"))
    print(f"   HTML size: {html_size:,} bytes")

    if html_size > CONFIGMAP_MAX_BYTES:
        print(f"   ⚠️  WARNING: HTML exceeds ConfigMap limit ({CONFIGMAP_MAX_BYTES:,} bytes).")
        print(f"   Consider using an initContainer + emptyDir volume instead.")
        print(f"   (Script will still generate — deployment may fail on apply.)")

    # 2. Output directory
    out_dir = OVERLAYS_DIR / site_name
    if out_dir.exists():
        print(f"   ⚠️  Overwriting existing overlay at: {out_dir}")
        shutil.rmtree(out_dir)

    # 3. Generate manifests
    manifests = {
        "namespace.yaml": render_namespace(namespace),
        "content-configmap.yaml": render_content_configmap(site_name, namespace, html),
        "nginx-configmap.yaml": render_nginx_configmap(site_name, namespace, domain),
        "deployment.yaml": render_k8s_deployment(site_name, namespace),
        "service.yaml": render_k8s_service(site_name, namespace),
        "healthcheck.yaml": render_k8s_healthcheck(site_name, namespace),
        "httproute.yaml": render_httproute(site_name, namespace, domain),
    }

    resource_names = list(manifests.keys())
    manifests["kustomization.yaml"] = render_kustomization(site_name, namespace, resource_names)

    for filename, content in manifests.items():
        write_manifest(out_dir / filename, content)

    # 4. Write the HTML standalone (useful for local preview)
    write_manifest(out_dir / "site.html", html)

    print(f"\n✅ Generated {len(manifests) + 1} files in: {out_dir}")
    print(f"   {len(manifests)} K8s manifests + site.html (preview)")
    print(f"\n   📋 Resources created:")
    for name in resource_names:
        print(f"      - {name}")

    return {
        "site_name": site_name,
        "namespace": namespace,
        "domain": domain,
        "out_dir": str(out_dir),
        "html_size": html_size,
        "files": list(manifests.keys()) + ["site.html"],
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate.py <config.yaml>")
        print("Example: python scripts/generate.py configs/example-landscaping.yaml")
        sys.exit(1)

    generate(sys.argv[1])
