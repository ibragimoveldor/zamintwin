# PCI Web App — Deployment Guide

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Django 5.1  │────▶│  Celery      │────▶│  AI Service      │
│  (Web UI)    │     │  (Worker)    │     │  (FastAPI + GPU)  │
│  Port 8000   │     │              │     │  Port 8001        │
└──────┬───────┘     └──────┬───────┘     └──────────────────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  PostgreSQL  │     │  Redis       │     │  Shared Volume   │
│  Port 5432   │     │  Port 6379   │     │  /data/media     │
└─────────────┘     └──────────────┘     └──────────────────┘
```

- **Django** — project management, user auth, results display
- **Celery** — async task queue (triggers AI analysis)
- **AI Service** — FastAPI with GPU, runs YOLO + SegFormer + PCI calculation
- **Redis** — Celery broker
- **PostgreSQL** — database
- **Shared Volume** — uploaded images & results accessible by all services

---

## Prerequisites

On your GPU server (210.107.217.223):

```bash
# Docker & Docker Compose
docker --version        # >= 24.0
docker compose version  # >= 2.20

# NVIDIA Container Toolkit (for GPU access in Docker)
nvidia-smi              # should show your GPU
nvidia-ctk --version    # >= 1.14
```

If NVIDIA Container Toolkit is not installed:
```bash
# Ubuntu
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## Step 1: Upload & Extract

```bash
# Upload zip to server
scp pci_final_clean.zip user@210.107.217.223:~/

# On server
cd ~
unzip pci_final_clean.zip -d pci_project
cd pci_project
```

Directory structure after extraction:
```
pci_project/
├── ai_service/          # FastAPI AI engine
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/             # pipeline, detection, segmentation, PCI calc
├── pci_web/             # Django web app
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── config/          # settings, urls, celery, wsgi
│   ├── apps/            # accounts, projects, analysis, reports
│   ├── templates/       # HTML templates
│   └── static/          # CSS, JS, images, fonts
├── docker/              # Docker Compose files
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   └── .env.example
└── scripts/
    └── init_repo.sh
```

---

## Step 2: Configure Environment

```bash
cd docker

# Create .env from example
cp .env.example .env

# Edit .env
nano .env
```

**.env file contents:**
```env
# Security — generate a real key!
SECRET_KEY=your-random-secret-key-here

# Database
DB_PASSWORD=your-secure-db-password

# Django
DEBUG=False
ALLOWED_HOSTS=210.107.217.223,localhost,your-domain.com
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## Step 3: Place Model Weights

The AI service expects model weights mounted at `/models` inside the container.
Place your model files in `docker/models/`:

```bash
mkdir -p docker/models/PCI

# Copy your model files
cp /path/to/n02m.pt docker/models/           # YOLO detection model
cp /path/to/crackseg.pth docker/models/       # Segmentation model
cp /path/to/PCI/*.csv docker/models/PCI/      # PCI deduct value tables
```

Expected structure:
```
docker/models/
├── n02m.pt              # YOLO detection weights
├── crackseg.pth         # SegFormer segmentation weights
└── PCI/
    └── *.csv            # PCI deduct value lookup tables
```

---

## Step 4: Build & Start

```bash
cd docker

# Build all images (first time takes ~10-15 min)
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps

# Check logs
docker compose logs -f web          # Django logs
docker compose logs -f ai-service   # AI service logs
docker compose logs -f celery       # Celery worker logs
```

Expected output of `docker compose ps`:
```
NAME              STATUS    PORTS
postgres          running   5432
redis             running   6379
web               running   0.0.0.0:8000->8000
celery            running
ai-service        running   0.0.0.0:8001->8001
```

---

## Step 5: Initialize Database

```bash
# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Collect static files (already done in Dockerfile, but just in case)
docker compose exec web python manage.py collectstatic --noinput
```

---

## Step 6: Verify

1. **Web UI**: http://210.107.217.223:8000
2. **Admin**: http://210.107.217.223:8000/admin/
3. **AI Service health**: http://210.107.217.223:8001/docs (FastAPI Swagger)

**Quick test:**
```bash
# Test AI service is responding
curl http://localhost:8001/docs

# Test Django is responding
curl http://localhost:8000

# Test GPU is accessible in AI container
docker compose exec ai-service python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}')"
```

---

## Step 7: Migrate Old Data (Optional)

If you have existing projects in the old `uploads/` folder:

```bash
# Copy old uploads to the shared volume
docker compose exec web bash

# Inside container:
# Old structure: uploads/<project_name>/images/, /result/, /pci/
# New structure: /data/media/<project_name>/images/, /result/, /pci/
# They're the same — just copy
cp -r /path/to/old/uploads/* /data/media/
```

Then create project records via Django admin or shell:
```bash
docker compose exec web python manage.py shell
```
```python
from django.contrib.auth.models import User
from apps.projects.models import Project

user = User.objects.get(username='your_username')

# Create project records for existing data
Project.objects.create(
    user=user,
    name='YourProject',
    status=4,  # 4 = Completed
)
```

---

## Common Operations

### Restart services
```bash
docker compose restart web celery ai-service
```

### View real-time logs
```bash
docker compose logs -f --tail=100
```

### Update code (after changes)
```bash
docker compose build web celery    # rebuild Django image
docker compose up -d               # restart with new image
docker compose exec web python manage.py migrate  # if models changed
```

### Backup database
```bash
docker compose exec postgres pg_dump -U pci_user pci_db > backup_$(date +%Y%m%d).sql
```

### Restore database
```bash
cat backup.sql | docker compose exec -T postgres psql -U pci_user pci_db
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `CUDA not available` | Check `nvidia-smi` on host, verify nvidia-container-toolkit |
| `connection refused :5432` | Wait for postgres to start: `docker compose logs postgres` |
| `TemplateDoesNotExist` | Run `docker compose exec web python manage.py collectstatic --noinput` |
| `Module not found: apps.xxx` | Make sure `WORKDIR` is `/app` in Dockerfile |
| AI service OOM | Reduce `--limit-concurrency` in ai_service CMD or use smaller batch |
| Static files 404 | In production, use nginx or whitenoise to serve static files |

### Production: Add Nginx (recommended)

For production, add nginx in front of Django to serve static files:

```bash
# docker-compose.override.yml or add to docker-compose.yml
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ../pci_web/staticfiles:/static:ro
      - shared_data:/data/media:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - web
```

**nginx.conf:**
```nginx
server {
    listen 80;
    client_max_body_size 500M;

    location /static/ {
        alias /static/;
    }

    location /uploads/ {
        alias /data/media/;
    }

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## Tech Stack Summary

| Component | Version | Purpose |
|-----------|---------|---------|
| Django | 5.1 | Web framework |
| DRF | 3.15+ | REST API |
| Celery | 5.3+ | Async task queue |
| FastAPI | 0.110+ | AI service API |
| PostgreSQL | 16 | Database |
| Redis | 7 | Celery broker |
| Python | 3.11 | Runtime |
| PyTorch | 2.1+ | Deep learning |
| Ultralytics | 8.1+ | YOLO detection |
| CUDA | 12.1 | GPU acceleration |
