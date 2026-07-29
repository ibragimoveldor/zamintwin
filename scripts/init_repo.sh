#!/bin/bash
# ============================================
# Run this ONCE to initialize the Git repo
# and push to your remote (GitHub/GitLab)
# ============================================

set -e

echo "=== PCI Web - Git Repository Setup ==="

# 1. Initialize git
git init
git add .
git commit -m "feat: initial project structure

- Django 5.1 web app with DRF API
- FastAPI AI inference service (GPU-isolated)
- Celery + Redis for async processing
- Docker Compose for full stack
- Separated AI code from web code"

# 2. Create dev branch
git checkout -b dev
git checkout main

echo ""
echo "=== Local repo ready ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Create a repo on GitHub/GitLab"
echo ""
echo "  2. Add the remote:"
echo "     git remote add origin https://github.com/YOUR_ORG/pci-web.git"
echo ""
echo "  3. Push both branches:"
echo "     git push -u origin main"
echo "     git push -u origin dev"
echo ""
echo "  4. On GitHub, go to Settings → Branches:"
echo "     - Set 'main' as default branch"
echo "     - Add branch protection rule for 'main':"
echo "       ✓ Require pull request reviews"
echo "       ✓ Require status checks to pass"
echo ""
echo "  5. Share with team:"
echo "     Tell them to read CONTRIBUTING.md after cloning"
echo ""
