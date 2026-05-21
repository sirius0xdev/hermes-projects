# api-gateway — Source Code Missing

## Status: Cannot Build Container

The api-gateway service has Kubernetes manifests and Helm charts but **no source code to containerize**.

### What Exists:
- `deploy/k8s/base/api-gateway-deployment.yaml` — K8s deployment referencing `ghcr.io/sirius0xdev/trading-api-gateway:latest`
- `deploy/helm/api-gateway/` — Per-service Helm chart
- `infra/helm/trading-platform/` — References in umbrella chart
- `deploy/dockerfiles/api-gateway.Dockerfile` — Nginx-based Dockerfile

### What's Missing:
- No application source code directory (no `trading-platform/api-gateway/`)
- The Dockerfile references `deploy/k8s/base/gateway/nginx.conf` and `deploy/k8s/base/gateway/conf.d/` — **these files do not exist**
- The Dockerfile cannot build without nginx configuration files

### Root Cause:
This will block GKE deployment. The api-gateway is intended to be an Nginx reverse proxy handling rate limiting and routing, but the nginx config files were never committed.

### Resolution Required:
1. Create the nginx configuration files (`nginx.conf` and route configs)
2. Update the Dockerfile COPY paths to match
3. Build and push the image
4. Or remove api-gateway from the deployment and use GKE Ingress + GCP Cloud Armor for rate limiting
