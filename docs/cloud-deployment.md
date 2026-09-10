# Cloud Deployment Guide (AWS EKS + ECR + ALB + ElastiCache)

This guide describes a production-style deployment for the Hit Counter app using **AWS EKS**, **ECR**, **ALB Ingress + ACM**, **Route53**, and **ElastiCache (Redis)**. It covers the React web UI, the FastAPI server, and Redis end-to-end.

---

## 1) Architecture Overview

**Components**
- **Web**: React app built with Vite and served by nginx.
- **API**: FastAPI server (`app.py`) exposing REST + WebSocket endpoints.
- **Redis**: Stores counts and chat names.

**AWS services used**
- **EKS**: Kubernetes cluster
- **ECR**: Container registry
- **ElastiCache (Redis)**: Managed Redis
- **ALB + ACM**: HTTPS ingress
- **Route53**: DNS

**Traffic flow**
- `https://app.example.com` → **ALB** → **web service** (nginx)
- `https://api.example.com` → **ALB** → **server service** (FastAPI)
- **server** → **ElastiCache (Redis)**

---

## 2) Prerequisites

- AWS account with permissions for EKS, ECR, ElastiCache, ACM, and Route53
- IAM user/role with the permissions below (for cluster + infra setup)
- Domain hosted in Route53 (e.g., `example.com`)
- ACM certificate in the **same region** as the ALB/EKS
- CLI tools:
  - `aws`, `kubectl`, `eksctl`, `helm`, `docker`

### IAM Permissions (Setup Operator)

**Option A (simplest):** Attach the managed policy `AdministratorAccess`.

**Option B (least-privilege, recommended for production):** Attach a custom policy that allows the following service-level permissions used in this guide:

- `eks:*` (cluster and node groups)
- `ecr:*` (repositories, auth, push/pull)
- `elasticache:*` (Redis cluster)
- `elasticloadbalancing:*` (ALB/target groups)
- `ec2:*` (VPC networking, security groups, subnets, ENIs)
- `autoscaling:*` (node group autoscaling)
- `iam:*` (roles/policies for EKS, node groups, and ALB controller)
- `acm:*` (TLS certs)
- `route53:*` (DNS records)
- `logs:*` (CloudWatch logs)
- `cloudformation:*` (used by `eksctl`)
- `sts:AssumeRole` (role assumption)

Example custom policy (broad but explicit):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EksEcrElbRedisDnsCerts",
      "Effect": "Allow",
      "Action": [
        "eks:*",
        "ecr:*",
        "elasticache:*",
        "elasticloadbalancing:*",
        "ec2:*",
        "autoscaling:*",
        "iam:*",
        "acm:*",
        "route53:*",
        "logs:*",
        "cloudformation:*",
        "sts:AssumeRole"
      ],
      "Resource": "*"
    }
  ]
}
```

### IAM Permissions (CI/CD Role for GitHub Actions)

Create a separate IAM role for GitHub Actions OIDC with permissions to:
- Push images to ECR (`ecr:*` or scoped to the two repos)
- Update EKS deployment (`eks:DescribeCluster`, `eks:AccessKubernetesApi`, plus `kubectl` auth)
- Read cluster config (`eks:Describe*`)
- Assume the role via `sts:AssumeRoleWithWebIdentity`

---

## 3) Build & Push Images to ECR

Create two ECR repositories:
- `hit-counter-web`
- `hit-counter-server`

Example (replace placeholders):

```bash
aws ecr create-repository --repository-name hit-counter-web
aws ecr create-repository --repository-name hit-counter-server

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build and push server
SERVER_TAG=123456789012.dkr.ecr.us-east-1.amazonaws.com/hit-counter-server:$(git rev-parse --short HEAD)
docker build -t "$SERVER_TAG" ./server
docker push "$SERVER_TAG"

# Build and push web
WEB_TAG=123456789012.dkr.ecr.us-east-1.amazonaws.com/hit-counter-web:$(git rev-parse --short HEAD)
docker build -t "$WEB_TAG" ./web
docker push "$WEB_TAG"
```

---

## 4) EKS Cluster Setup

Create cluster with managed node group:

```bash
eksctl create cluster \
  --name hit-counter \
  --region us-east-1 \
  --nodegroup-name standard \
  --nodes 2 \
  --managed
```

Enable OIDC provider:

```bash
eksctl utils associate-iam-oidc-provider \
  --cluster hit-counter \
  --region us-east-1 \
  --approve
```

Install AWS Load Balancer Controller:

```bash
helm repo add eks https://aws.github.io/eks-charts
helm repo update

# Create service account + IAM role (see AWS docs for exact policy)

helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=hit-counter \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller
```

Create namespace:

```bash
kubectl create namespace hit-counter
```

---

## 5) Redis (ElastiCache)

Create a **Redis** cluster inside the same VPC/subnets as EKS.

Important notes:
- Allow inbound **6379** from the EKS node security group.
- Use **non-TLS Redis** because the current client does not configure SSL.
- The server expects:
  
  ```
  REDIS_URL=redis://<primary-endpoint>:6379/0
  ```

---

## 6) Required App Configuration (Documented)

### Frontend API Base & WS URL
Update the frontend to allow **build-time env overrides**:

In `Counter.jsx`, replace the hard-coded API/WS URLs with `import.meta.env` overrides.

Example adjustment:

```jsx
const API_BASE = import.meta.env.VITE_API_BASE ?? `${window.location.protocol}//${window.location.hostname}:8080`;
const WS_URL = import.meta.env.VITE_WS_URL ?? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8080/ws`;
```

At build time (in CI/CD):

```
VITE_API_BASE=https://api.example.com
VITE_WS_URL=wss://api.example.com/ws
```

### Backend Environment Variables
Production values to set in Kubernetes:

```
DEV_CORS=false
ALLOW_DEV_IP_OVERRIDE=false
BUCKET_TZ=America/New_York
RETENTION_DAYS=7
```

### CORS Allowlist
Update FastAPI CORS allowlist to include your web app domain:

```
https://app.example.com
```

---

## 7) Kubernetes Manifests (Plain YAML)

Below are **example manifests**. Store them in a folder like `k8s/`.

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: hit-counter
```

### ConfigMap (non-secret envs)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: hit-counter-config
  namespace: hit-counter
data:
  BUCKET_TZ: "America/New_York"
  RETENTION_DAYS: "7"
  DEV_CORS: "false"
  ALLOW_DEV_IP_OVERRIDE: "false"
```

### Secret (Redis URL)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: hit-counter-secrets
  namespace: hit-counter
type: Opaque
stringData:
  REDIS_URL: "redis://YOUR-ELASTICACHE-ENDPOINT:6379/0"
```

### Server Deployment + Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hit-counter-server
  namespace: hit-counter
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hit-counter-server
  template:
    metadata:
      labels:
        app: hit-counter-server
    spec:
      containers:
        - name: server
          image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/hit-counter-server:REPLACE_TAG
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: hit-counter-config
            - secretRef:
                name: hit-counter-secrets
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: hit-counter-server
  namespace: hit-counter
spec:
  selector:
    app: hit-counter-server
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

### Web Deployment + Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hit-counter-web
  namespace: hit-counter
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hit-counter-web
  template:
    metadata:
      labels:
        app: hit-counter-web
    spec:
      containers:
        - name: web
          image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/hit-counter-web:REPLACE_TAG
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "250m"
              memory: "256Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: hit-counter-web
  namespace: hit-counter
spec:
  selector:
    app: hit-counter-web
  ports:
    - name: http
      port: 80
      targetPort: 80
```

### Ingress (ALB + ACM)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hit-counter-ingress
  namespace: hit-counter
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:us-east-1:123456789012:certificate/EXAMPLE
    alb.ingress.kubernetes.io/healthcheck-path: /health
    alb.ingress.kubernetes.io/load-balancer-attributes: idle_timeout.timeout_seconds=120
spec:
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hit-counter-web
                port:
                  number: 80
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hit-counter-server
                port:
                  number: 8080
```

Apply all manifests:

```bash
kubectl apply -f k8s/
```

---

## 8) DNS (Route53)

Create two Route53 records:
- `app.example.com` → ALB DNS name (ALIAS)
- `api.example.com` → ALB DNS name (ALIAS)

---

## 9) CI/CD with GitHub Actions (OIDC → ECR → EKS)

Example workflow (`.github/workflows/deploy.yml`):

```yaml
name: Deploy

on:
  push:
    branches: ["main"]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      AWS_REGION: us-east-1
      EKS_CLUSTER: hit-counter
      ECR_REGISTRY: 123456789012.dkr.ecr.us-east-1.amazonaws.com
      WEB_REPO: hit-counter-web
      SERVER_REPO: hit-counter-server
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-eks
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build & push server
        run: |
          TAG=${GITHUB_SHA::7}
          docker build -t $ECR_REGISTRY/$SERVER_REPO:$TAG ./server
          docker push $ECR_REGISTRY/$SERVER_REPO:$TAG

      - name: Build & push web
        run: |
          TAG=${GITHUB_SHA::7}
          docker build -t $ECR_REGISTRY/$WEB_REPO:$TAG ./web
          docker push $ECR_REGISTRY/$WEB_REPO:$TAG

      - name: Update kubeconfig
        run: aws eks update-kubeconfig --name $EKS_CLUSTER --region $AWS_REGION

      - name: Deploy
        run: |
          TAG=${GITHUB_SHA::7}
          kubectl set image deployment/hit-counter-server server=$ECR_REGISTRY/$SERVER_REPO:$TAG -n hit-counter
          kubectl set image deployment/hit-counter-web web=$ECR_REGISTRY/$WEB_REPO:$TAG -n hit-counter
```

Note: This assumes the `hit-counter` namespace and deployments already exist.

---

## 10) Verification Checklist

- `https://app.example.com` loads the React app
- `https://app.example.com/chat` loads (SPA routing works)
- `https://api.example.com/health` returns `ok`
- `wss://api.example.com/ws` receives live count updates
- `POST /chat/name` persists and `GET /chat/name` returns registered name
- CORS allows `https://app.example.com` to call the API

---

## Assumptions & Defaults

- AWS region: `us-east-1`
- Account ID: `123456789012`
- Domain: `example.com`
- EKS + ALB Ingress + ACM + Route53
- **ElastiCache without TLS** (compatible with current Redis client)
- Separate subdomains for web and API

---

## Optional Enhancements (Not Implemented)

- S3 + CloudFront hosting instead of nginx
- Secrets Manager integration
- HPA and monitoring (CloudWatch/Prometheus)
