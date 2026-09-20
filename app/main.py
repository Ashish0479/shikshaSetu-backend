import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.routes import upload, datasets, quality
from app.database.mongodb import db_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("shikshasetu-api")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=(
        "Layer 1 & 2 Data Quality, Ingestion, Validation, and Standardization Engine "
        "for ShikshaSetu (Haryana Teacher Deployment Planning Architecture)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(upload.router, prefix=settings.API_V1_STR)
app.include_router(datasets.router, prefix=settings.API_V1_STR)
app.include_router(quality.router, prefix=settings.API_V1_STR)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Teacher Data Quality & Standardization System...")
    logger.info(f"MongoDB status: {'Connected' if db_client.is_connected else 'In-Memory Cache (MongoDB Offline)'}")

@app.get("/", tags=["Health & Status"])
async def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "status": "operational",
        "mongodb_connected": db_client.is_connected,
        "notice": "Administrative Data Quality Tool. Does not perform automated teacher transfers or HR actions."
    }

@app.get("/api/health", tags=["Health & Status"])
async def health_check():
    return {
        "status": "healthy",
        "mongodb_connected": db_client.is_connected,
        "storage_mode": "mongodb" if db_client.is_connected else "in_memory_resilient_cache"
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing the request."}
    )
