# Local Business Websites — Automated GKE Deployment Pipeline

Config-file-driven pipeline to deploy static business websites on GKE with Gateway API routing.

## Architecture

```
configs/landscaping.yaml  ──→  scripts/generate.py  ──→  overlays/landscaping-business/
                                                              ├── namespace.yaml
                                                              ├── content-configmap.yaml
                                                              ├── nginx-configmap.yaml
                                                              ├── deployment.yaml
                                                              ├── service.yaml
                                                              ├── healthcheck.yaml
                                                              ├── httproute.yaml
                                                              ├── kustomization.yaml
                                                              └── site.html

                                                         scripts/deploy.py
                                                              │
                                                              ▼
                                              kubectl apply -k overlays/landscaping-business
                                                              │
                                                              ▼
                                              GKE Cluster ── Gateway API ── https://landscaping-business.siriusdevops.com
```

## Prerequisites

1. **GKE cluster** running with Gateway API enabled (gke-l7-global-external-managed)
2. **Gateway** `external-http-gateway` deployed in `customer1` namespace
3. **kubectl** configured for the cluster
4. **Python 3.9+** with PyYAML (`pip install pyyaml`)

## Quick Start

```bash
# 1. Generate and deploy a single site
python scripts/generate.py configs/example-landscaping.yaml
python scripts/deploy.py overlays/landscaping-business

# 2. Or: one command end-to-end
python scripts/deploy.py configs/example-landscaping.yaml

# 3. Visit the site
open https://landscaping-business.siriusdevops.com
```

## Commands

| Command | Description |
|---|---|
| `python scripts/generate.py configs/<name>.yaml` | Generate K8s manifests + HTML |
| `python scripts/deploy.py configs/<name>.yaml` | Generate + deploy to cluster |
| `python scripts/deploy.py --all` | Deploy all configs in configs/ |
| `python scripts/deploy.py --list` | List generated overlays |
| `python scripts/deploy.py --delete <site-name>` | Delete site + namespace |
| `python scripts/deploy.py configs/<name>.yaml --dry-run` | Dry-run (no apply) |

## Adding a New Business

Create a YAML config in `configs/`:

```yaml
business:
  name: my-business              # kebab-case, becomes subdomain
  namespace: my-business         # K8s namespace
  domain_base: siriusdevops.com  # parent domain
  title: "My Business Name"
  tagline: "A short tagline"
  phone: "(555) 000-0000"
  email: "hello@example.com"
  address: "123 Main St"
  colors:
    primary: "#1a73e8"
    secondary: "#f5f5f5"
    accent: "#ff6d00"
    text: "#333333"
  logo_text: "MyBiz"

pages:
  home:
    hero:
      headline: "Welcome to My Business"
      subheadline: "We provide excellent service"
      cta: "Call Us Now"
    sections:
      - type: services
        title: "What We Offer"
        items:
          - title: "Service 1"
            description: "Description here"
            icon: "🔧"
      - type: about
        title: "About Us"
        content: "Your story here..."
      - type: contact
        title: "Contact"
        show_phone: true
        show_email: true
        show_address: true
        show_hours: false
```

Then deploy:

```bash
python scripts/deploy.py configs/my-business.yaml
```

## Resource Specs

| Resource | Spec |
|---|---|
| nginx | alpine 1.27, ~3 MB image |
| CPU request | 5m |
| CPU limit | 50m |
| Memory request | 16 Mi |
| Memory limit | 64 Mi |

Sites are extremely lightweight — 100 businesses = ~0.5 CPU core + 1.6 GB RAM at idle.

## Under the Hood

- **Static HTML** rendered server-side by the generator (no client-side JS frameworks)
- **ConfigMap** stores the HTML (up to ~1 MiB; larger sites auto-warn)
- **nginx:alpine** serves the ConfigMap as a read-only volume mount
- **Gateway API** HTTPRoute routes `<name>.<domain>` → Service → Pod
- **HealthCheckPolicy** ensures GKE L7 load balancer health checks pass
- **Kustomize** ties all manifests together for clean `apply -k`

## Gateway API Configuration

The Gateway (`external-http-gateway`) must exist in `customer1` namespace:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: external-http-gateway
  namespace: customer1
  annotations:
    networking.gke.io/certmap: gateway-cert-map
spec:
  gatewayClassName: gke-l7-global-external-managed
  listeners:
  - name: https
    protocol: HTTPS
    port: 443
    allowedRoutes:
      namespaces:
        from: All
```

Each site's HTTPRoute references this Gateway. Routes land in the business namespace but bind to the Gateway in `customer1` (cross-namespace route attachment is enabled by `allowedRoutes.namespaces.from: All`).
