#!/bin/bash
# =============================================================================
# UzRoad.ai Sessions App — Install into Django PCI project
#
# Run from your pci_git_ready_fixed_v2/ root:
#   chmod +x install_sessions_django.sh
#   ./install_sessions_django.sh
# =============================================================================

set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  UzRoad.ai Sessions — Django App Install"
echo "=========================================="

# Check we're in the right place
if [ ! -d "pci_web/apps" ]; then
    echo "❌ Run this from your project root (where pci_web/ lives)"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 1: Copying sessions app...${NC}"
# The sessions app files should be alongside this script
cp -r apps/sessions pci_web/apps/sessions
echo -e "${GREEN}  ✓ pci_web/apps/sessions/ created${NC}"

echo ""
echo -e "${YELLOW}Step 2: Copying templates...${NC}"
cp -r templates/sessions pci_web/templates/sessions
echo -e "${GREEN}  ✓ pci_web/templates/sessions/ created${NC}"

echo ""
echo -e "${YELLOW}Step 3: Patching settings...${NC}"
if grep -q "apps.sessions" pci_web/config/settings/base.py; then
    echo -e "${GREEN}  ✓ Already in INSTALLED_APPS — skipping${NC}"
else
    sed -i '/"apps.reports",/a\    "apps.sessions",' pci_web/config/settings/base.py
    echo -e "${GREEN}  ✓ Added 'apps.sessions' to INSTALLED_APPS${NC}"
fi

echo ""
echo -e "${YELLOW}Step 4: Patching URLs...${NC}"
if grep -q "sessions" pci_web/config/urls.py; then
    echo -e "${GREEN}  ✓ Sessions URL already in urls.py — skipping${NC}"
else
    sed -i '/path("reports\/", include("apps.reports.urls")),/a\    path("sessions/", include("apps.sessions.urls")),' pci_web/config/urls.py
    echo -e "${GREEN}  ✓ Added sessions URL to config/urls.py${NC}"
fi

echo ""
echo -e "${YELLOW}Step 5: Adding sidebar nav link...${NC}"
if grep -q "sessions:list" pci_web/templates/base.html; then
    echo -e "${GREEN}  ✓ Sidebar link already exists — skipping${NC}"
else
    sed -i '/<a href="{% url '"'"'reports:index'"'"' %}">/i\            <a href="{% url '"'"'sessions:list'"'"' %}"><i class="fa fa-map-marked-alt"><\/i> <span>Road Inspection<\/span><\/a>' pci_web/templates/base.html
    echo -e "${GREEN}  ✓ Added 'Road Inspection' to sidebar${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  ✅ Installation complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Run migrations:"
echo "     docker compose -f docker/docker-compose.yml exec web python manage.py makemigrations sessions"
echo "     docker compose -f docker/docker-compose.yml exec web python manage.py migrate"
echo ""
echo "  2. Restart web service:"
echo "     docker compose -f docker/docker-compose.yml restart web"
echo ""
echo "  3. Open http://localhost:8000/sessions/"
echo ""
echo "  4. Upload sample_session_20250322_143025.zip"
echo ""
