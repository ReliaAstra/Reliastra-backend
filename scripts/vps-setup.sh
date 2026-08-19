#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Reliastra VPS First-Time Setup Script
# Run this ONCE on your VPS to prepare it for CD deployments
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

echo "=== Reliastra VPS Setup ==="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. Check prerequisites
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found. Installing...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker $USER
    echo -e "${GREEN}Docker installed.${NC}"
else
    echo -e "${GREEN}Docker found: $(docker --version)${NC}"
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose not found.${NC}"
    exit 1
else
    echo -e "${GREEN}Docker Compose found: $(docker compose version)${NC}"
fi

# 2. Create deploy directory
echo -e "${YELLOW}[2/6] Creating deploy directory...${NC}"
mkdir -p ~/reliastra
cd ~/reliastra
echo -e "${GREEN}Deploy directory: ~/reliastra${NC}"

# 3. Create production env file
echo -e "${YELLOW}[3/6] Creating .env.production template...${NC}"
if [ ! -f .env.production ]; then
    cat > .env.production << 'EOF'
# ═══ Reliastra Production Environment ═══
# Generate a strong secret: python -c "import secrets; print(secrets.token_urlsafe(48))"

# ── Required ──────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://reliastra:CHANGE_ME_DB_PASSWORD@postgres:5432/reliastra
REDIS_URL=redis://redis:6379/0
SECRET_KEY=CHANGE_ME_GENERATE_A_48_CHAR_SECRET
ENVIRONMENT=production
CORS_ORIGINS=["https://yourdomain.com"]

# ── Postgres ───────────────────────────────────────────────────
POSTGRES_PASSWORD=CHANGE_ME_DB_PASSWORD

# ── Server ─────────────────────────────────────────────────────
API_PORT=8000

# ── OAuth (optional) ──────────────────────────────────────────
GOOGLE_AUTH_ENABLED=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GITHUB_AUTH_ENABLED=false
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=

# ── Supabase Storage S3 (required for evidence PDFs) ─────────────
# From the Supabase dashboard: Storage → S3 Access Keys.
# Buckets are created in the dashboard, never by the app.
SUPABASE_S3_ENDPOINT=
SUPABASE_S3_REGION=
SUPABASE_S3_ACCESS_KEY_ID=
SUPABASE_S3_SECRET_ACCESS_KEY=
SUPABASE_S3_BUCKET=

# ── SMTP (optional) ───────────────────────────────────────────
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_FROM=noreply@reliastra.com

# ── Paystack Billing (optional) ──────────────────────────────
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=
EOF
    echo -e "${GREEN}.env.production created — EDIT IT before first deploy!${NC}"
    echo -e "${RED}IMPORTANT: Change SECRET_KEY, POSTGRES_PASSWORD, and DATABASE_URL${NC}"
else
    echo -e "${GREEN}.env.production already exists.${NC}"
fi

# 4. Copy production docker-compose
echo -e "${YELLOW}[4/6] Setting up docker-compose.production.yml...${NC}"
if [ ! -f docker-compose.production.yml ]; then
    echo "Copy docker-compose.production.yml from the repo to ~/reliastra/"
    echo "Or let the CD workflow create it automatically on first deploy."
else
    echo -e "${GREEN}docker-compose.production.yml already exists.${NC}"
fi

# 5. Log in to GHCR
echo -e "${YELLOW}[5/6] GitHub Container Registry login...${NC}"
echo "Run this manually (token needs package:read scope):"
echo "  echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin"
echo ""

# 6. Firewall check
echo -e "${YELLOW}[6/6] Firewall reminder...${NC}"
echo "Make sure port 8000 (or your API_PORT) is open:"
echo "  sudo ufw allow 8000/tcp"
echo "  sudo ufw allow 443/tcp  # if using nginx/reverse proxy"
echo ""

echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit ~/reliastra/.env.production with real values"
echo "  2. Copy docker-compose.production.yml to ~/reliastra/"
echo "  3. Log in to GHCR: echo PAT | docker login ghcr.io -u USER --password-stdin"
echo "  4. Run: cd ~/reliastra && docker compose -f docker-compose.production.yml up -d"
echo ""
echo "After that, the CD pipeline will handle future deploys automatically."
