"""
PCI AI Inference Service.

FastAPI application that:
- Loads ML models ONCE at startup (not per-request)
- Exposes REST endpoints for the PCI pipeline
- Runs independently on a GPU machine
- Can be scaled horizontally with multiple workers
"""

import os
import logging
from enum import Enum
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Configuration ---
class Settings(BaseModel):
    detection_model: str = os.getenv("AI_DETECTION_MODEL", "models/n02m.pt")
    segmentation_model: str = os.getenv("AI_SEGMENTATION_MODEL", "models/crackseg.pth")
    deduct_values_path: str = os.getenv("AI_DEDUCT_VALUES_PATH", "models/PCI/")
    gpu_id: int = int(os.getenv("AI_GPU_ID", "0"))
    shared_storage: str = os.getenv("SHARED_STORAGE", "/data")


settings = Settings()


# --- Models loaded at startup, not per-request ---
pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models once when the service starts."""
    global pipeline
    logger.info("Loading AI models... (this takes 10-30 seconds)")

    from app.pipeline import PCIPipeline
    pipeline = PCIPipeline(
        det_model_path=settings.detection_model,
        seg_model_path=settings.segmentation_model,
        dv_path=settings.deduct_values_path,
        gpu_id=settings.gpu_id,
    )
    logger.info("AI models loaded successfully")
    yield
    logger.info("Shutting down AI service")
    pipeline = None


app = FastAPI(
    title="PCI AI Service",
    description="Pavement Condition Index analysis pipeline",
    version="2.0.0",
    lifespan=lifespan,
)


# --- Request/Response schemas ---
class AnalyzeRequest(BaseModel):
    project_id: int = Field(..., description="Project ID for tracking")
    images_dir: str = Field(..., description="Path to images directory on shared storage")


class PipelineStep(str, Enum):
    PREPROCESSING = "preprocessing"
    DETECTION = "detection"
    WIDTH_CALCULATION = "width_calculation"
    PCI_EVALUATION = "pci_evaluation"


class StepRequest(BaseModel):
    """Run a single pipeline step (for debugging/reprocessing)."""
    images_dir: str
    step: PipelineStep


class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    gpu_available: bool


class AnalyzeResponse(BaseModel):
    status: str
    project_id: int
    message: str


# --- Endpoints ---
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check if the service is healthy and models are loaded."""
    import torch
    return HealthResponse(
        status="healthy" if pipeline is not None else "loading",
        models_loaded=pipeline is not None,
        gpu_available=torch.cuda.is_available(),
    )


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Run the full PCI pipeline synchronously.

    The Celery worker on the Django side calls this endpoint and waits
    for the result. This is fine because:
    - Celery tasks are already async from the web server's perspective
    - We want to know immediately if processing failed
    - The AI service can handle concurrent requests via uvicorn workers
    """
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Models still loading")

    images_dir = request.images_dir
    if not os.path.isdir(images_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {images_dir}")

    try:
        logger.info(f"Starting pipeline for project {request.project_id}: {images_dir}")
        result = pipeline.run(images_dir)
        return AnalyzeResponse(
            status="completed",
            project_id=request.project_id,
            message=f"Pipeline completed in {result['elapsed']:.1f}s",
        )
    except Exception as e:
        logger.error(f"Pipeline failed for project {request.project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analyze/async", response_model=AnalyzeResponse)
async def analyze_async(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Run pipeline in the background (fire-and-forget).
    Use this if you want the AI service itself to be non-blocking.
    The Django side would then poll for results via /api/v1/status/{project_id}.
    """
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Models still loading")

    background_tasks.add_task(pipeline.run, request.images_dir)

    return AnalyzeResponse(
        status="processing",
        project_id=request.project_id,
        message="Pipeline started in background",
    )


@app.post("/api/v1/step")
async def run_step(request: StepRequest):
    """Run a single pipeline step. Useful for debugging or reprocessing."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Models still loading")

    try:
        result = pipeline.run_step(request.images_dir, request.step.value)
        return {"status": "completed", "step": request.step, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
