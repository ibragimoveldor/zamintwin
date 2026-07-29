# PCI Web - Pavement Condition Index Evaluation System

## Architecture Overview

```
pci_restructured/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                     # Django project config (was 'main/')
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── development.py      # Dev overrides
│   │   └── production.py       # Prod overrides
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py               # Celery app configuration
│
├── apps/                       # Django apps (clean separation)
│   ├── accounts/               # User auth & management
│   ├── projects/               # Project CRUD & image upload (was 'pci/')
│   ├── analysis/               # Results, PCI display, map view (was 'analyze/')
│   └── reports/                # Report generation & CSV export
│
├── ai_engine/                  # ML pipeline (completely decoupled from Django)
│   ├── __init__.py
│   ├── pipeline.py             # Main orchestrator (entry point for Celery tasks)
│   ├── detection/              # YOLO crack detection
│   │   ├── __init__.py
│   │   └── detector.py         # CrackDetector class
│   ├── segmentation/           # Crack segmentation (UNet + traditional)
│   │   ├── __init__.py
│   │   └── segmenter.py        # SegmentationModel class
│   ├── evaluation/             # PCI calculation
│   │   ├── __init__.py
│   │   └── pci_calculator.py   # PCI evaluation logic
│   ├── preprocessing/          # Image splitting, joining, resizing
│   │   ├── __init__.py
│   │   └── image_ops.py        # splitter, joiner, image_10m
│   └── utils/                  # Width calculation, thinning, helpers
│       ├── __init__.py
│       ├── width.py            # widthCalculator
│       ├── thinning.py         # Zhang-Suen thinning
│       ├── fast_thin.py        # Fast thinning (ftlib)
│       └── morphology.py       # Segment enhancing
│
├── templates/                  # All templates
├── static/                     # Static assets
├── media/                      # User uploads (was 'uploads/')
└── scripts/                    # Management scripts
```

## Key Changes from Original

1. **Django 2.2 → 5.1**: Modern Django with async support
2. **Python 3.8 → 3.11+**: Performance + security
3. **AI code decoupled**: `ai_engine/` is a standalone Python package, no Django imports
4. **Celery for ML tasks**: No more subprocess calls blocking requests
5. **Environment-based config**: Secrets in `.env`, split settings
6. **Clean app boundaries**: Each app has a single responsibility
7. **No hardcoded paths**: Everything configurable via settings/env

## Quick Start

```bash
cp .env.example .env  # Edit with your values
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# In separate terminal:
celery -A config worker -l info
```
