import os
import time
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from utils.limiter import limiter

app = FastAPI(title="ClassReminder API", version="1.0.0")

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — configurable via environment variable
cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False if allow_origins == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 1)
    print(f"  {request.method} {request.url.path} -> {response.status_code} ({duration}ms)")
    return response


# Routers
from routes.auth import router as auth_router
from routes.events import router as events_router
from routes.ai import router as ai_router
from routes.timetable import router as timetable_router
from routes.tasks import router as tasks_router
from routes.assignments import router as assignments_router
from routes.exams import router as exams_router
from routes.calendar import router as calendar_router
from routes.stats import router as stats_router
from routes.notes import router as notes_router
from routes.search import router as search_router
from routes.backup import router as backup_router
from routes.dashboard import router as dashboard_router
from routes.rewards import router as rewards_router

app.include_router(auth_router)
app.include_router(events_router)
app.include_router(ai_router)
app.include_router(timetable_router)
app.include_router(tasks_router)
app.include_router(assignments_router)
app.include_router(exams_router)
app.include_router(calendar_router)
app.include_router(stats_router)
app.include_router(notes_router)
app.include_router(search_router)
app.include_router(backup_router)
app.include_router(dashboard_router)
app.include_router(rewards_router)


@app.get("/")
def root():
    return {"message": "Welcome to ClassReminder API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
