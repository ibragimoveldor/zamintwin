# Contributing Guide

## Getting Started (New Team Member)

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_ORG/pci-web.git
cd pci-web
```

### 2. Get model weights (not in Git — too large)

Model files are stored on the shared NAS. Copy them to your local machine:

```bash
# Ask the team lead for the NAS path or download link
mkdir -p docker/models/PCI/dv_curve docker/models/PCI/cdv_py2

# Copy from shared drive
cp /nas/ai_models/pci/best.pt docker/models/
cp /nas/ai_models/pci/crackseg.pth docker/models/
cp /nas/ai_models/pci/dv_curve/*.pkl docker/models/PCI/dv_curve/
cp /nas/ai_models/pci/cdv_py2/*.pkl docker/models/PCI/cdv_py2/
```

### 3. Create your local environment file

```bash
cp docker/.env.example docker/.env
# Edit docker/.env with your local settings
```

### 4. Run everything

```bash
cd docker
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### 5. Verify

```bash
curl http://localhost:8001/health   # AI service
curl http://localhost:8000          # Django
```

---

## Git Workflow

We use a simple branching model:

```
main          ← production-ready code (protected)
  └── dev     ← integration branch
       ├── feature/add-pothole-detection
       ├── feature/improve-crack-segmentation
       └── fix/pci-calculation-edge-case
```

### Daily workflow

```bash
# Start a new feature
git checkout dev
git pull origin dev
git checkout -b feature/your-feature-name

# Work on your changes...
git add .
git commit -m "feat: add pothole severity classification"

# Push and create PR
git push origin feature/your-feature-name
# → Create Pull Request on GitHub: feature/... → dev
```

### Commit message format

```
feat: add pothole severity classification
fix: correct PCI calculation for edge case with no cracks
refactor: extract image preprocessing into separate module
docs: update API documentation
```

---

## Project Structure — Who Works Where

```
pci-web/
├── ai_service/          ← AI/ML engineers work here
│   ├── app/
│   │   ├── detection/   ← YOLO model, crack detection logic
│   │   ├── evaluation/  ← PCI calculation, deduct values
│   │   ├── preprocessing/ ← Image splitting, joining
│   │   └── utils/       ← Width calc, thinning, morphology
│   └── Dockerfile
│
├── pci_web/             ← Web/backend engineers work here
│   ├── apps/
│   │   ├── accounts/    ← Auth, user management
│   │   ├── projects/    ← Project CRUD, file upload, Celery tasks
│   │   ├── analysis/    ← Results display, API endpoints
│   │   └── reports/     ← Report generation
│   ├── templates/       ← Frontend templates
│   ├── static/          ← CSS, JS, images
│   └── Dockerfile
│
└── docker/              ← DevOps / everyone
    └── docker-compose.yml
```

The key rule: **ai_service/ has zero Django imports. pci_web/ has zero ML imports.**
This means AI and web developers never have merge conflicts on each other's code.

---

## Testing Changes

### AI service changes

```bash
# Rebuild and restart only the AI service
docker compose build ai-service
docker compose up -d ai-service

# Check logs
docker compose logs -f ai-service

# Test the API directly
curl -X POST http://localhost:8001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "images_dir": "/data/media/test_project/images"}'
```

### Web app changes

```bash
# Rebuild and restart only the web app
docker compose build web
docker compose up -d web celery

# Or for quick iteration without rebuild (mount code as volume):
# Uncomment the volumes in docker-compose.override.yml
```

### Running without Docker (local development)

```bash
# AI service
cd ai_service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Web app (separate terminal)
cd pci_web
pip install -r requirements.txt
python manage.py runserver

# Celery (separate terminal)
cd pci_web
celery -A config worker -l info
```

---

## Environment Files

| File | In Git? | Purpose |
|------|---------|---------|
| `docker/.env.example` | Yes | Template with dummy values |
| `docker/.env` | **No** | Your local secrets |
| `docker/models/` | **No** | AI model weights (use shared NAS) |

Never commit `.env` or model files. They are in `.gitignore`.
