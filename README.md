# ZaminTwin.ai

**AI-powered digital twin platform for road infrastructure.**
Monitor, analyze, and predict road conditions across an entire network.

ZaminTwin ingests road survey footage, detects surface distresses with computer
vision, computes a **Pavement Condition Index (PCI)** per road segment, and
presents the results as an interactive network map with exportable reports.

🌐 [zamintwin.ai](https://zamintwin.ai)

---

## What it does

| Stage | Description |
|---|---|
| **Ingest** | Upload survey sessions (imagery + GPS tracks); frames are matched to road segments |
| **Detect** | YOLO object detection + UNet segmentation locate cracks, potholes, and surface defects |
| **Measure** | Morphological thinning and width analysis convert masks to physical distress dimensions |
| **Score** | Distress type, severity, and extent are combined into a PCI score (0–100) per segment |
| **Present** | Network map coloured by condition, per-session review, and PDF reports |

---

## Architecture

The system is split into **two independent services** that communicate over HTTP.

```
zamintwin_web/
├── pci_web/                  # Django 5.1 web application
│   ├── config/               # Settings, URLs, Celery app
│   ├── apps/
│   │   ├── accounts/         # Authentication and users
│   │   ├── projects/         # Project and network organisation
│   │   ├── sessions/         # Survey ingest, review, network map, PDF reports
│   │   ├── analysis/         # PCI analysis orchestration
│   │   └── reports/          # Report generation
│   ├── templates/
│   └── static/
│
├── ai_service/               # FastAPI inference service (GPU host)
│   └── app/
│       ├── main.py           # API endpoints
│       ├── pipeline.py       # Pipeline orchestrator
│       ├── detection/        # YOLO detection
│       ├── segmentation/     # UNet crack segmentation
│       ├── evaluation/       # PCI calculation
│       ├── preprocessing/    # Image splitting / joining
│       └── utils/            # Width calculation, thinning, morphology
│
└── docker/                   # Full-stack orchestration
    ├── docker-compose.yml    # nginx, postgres, redis, web, celery, ai-service
    └── nginx/                # Reverse proxy config
```

### Why two services?

| Concern | Direct import | API-based (this design) |
|---|---|---|
| GPU crash isolation | Takes down the web worker | AI service restarts alone |
| Scaling | Scale everything together | Scale GPU independently |
| Model loading | Every worker loads the model | Loaded once, shared |
| Deployment | One large container | Independent releases |
| Cloud cost | GPU for the whole server | GPU only where needed |

### Request flow

1. User uploads a survey session → Django writes to shared storage
2. User triggers analysis → Django enqueues a Celery task
3. Celery worker calls `POST /api/v1/analyze` on the AI service
4. AI service runs detection + segmentation, writes results to shared storage
5. Worker computes PCI, persists segment scores, marks the session complete
6. Network map and reports read from the database

Both services need access to the same filesystem for imagery and results —
a Docker volume in development, NFS/EFS or object storage in production.

---

## Quick start

**Requirements:** Docker + Docker Compose. A CUDA-capable GPU is needed for the
AI service; the web stack runs fine without one.

```bash
# 1. Configure environment
cp docker/.env.example docker/.env
$EDITOR docker/.env

# 2. Start the full stack
docker compose -f docker/docker-compose.yml up -d

# 3. Apply migrations and create an admin user
docker compose -f docker/docker-compose.yml exec web python manage.py migrate
docker compose -f docker/docker-compose.yml exec web python manage.py createsuperuser
```

The application is then available at `http://localhost`.

### Running services individually

```bash
# AI service
cd ai_service && uvicorn app.main:app --host 0.0.0.0 --port 8001

# Django
cd pci_web && python manage.py runserver 0.0.0.0:8000

# Celery worker
cd pci_web && celery -A config worker -l info
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment.

---

## Tech stack

**Backend** — Django 5.1 · Django REST Framework · Celery · PostgreSQL · Redis
**AI** — FastAPI · PyTorch 2.1+ · Ultralytics YOLO · UNet segmentation
**Infrastructure** — Docker Compose · nginx · Cloudflare

---

## Notes for reviewers

- **Model weights** (`ai_service/models/`, `*.pt`, `*.pth`) are excluded from
  version control and distributed separately.
- **Survey data and sample sessions** are excluded from this repository. Ask the
  maintainer for a demo dataset if you would like to run the ingest pipeline
  end to end.
- **Secrets** are supplied via `docker/.env`; see `docker/.env.example` for the
  required keys. No credentials are committed to this repository.

---

## License

Proprietary — all rights reserved. Shared for evaluation purposes only.
