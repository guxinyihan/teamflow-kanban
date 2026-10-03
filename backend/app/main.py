"""TeamFlow API. Schema changes are explicit Alembic commands, never startup DDL."""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from .config import settings
from .routers import auth, teams, tasks, boards
from .attachments import router as attachment_router
from .invitations import router as invitation_router
from .realtime import router as realtime_router

settings.validate_runtime()
logger = logging.getLogger("teamflow")
app = FastAPI(title="TeamFlow API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.FRONTEND_ORIGINS,
                   allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(boards.router, prefix="/api/boards", tags=["boards"])
app.include_router(boards.columns_router, prefix="/api/columns", tags=["columns"])
app.include_router(attachment_router.router, prefix="/api/attachments", tags=["attachments"])
app.include_router(invitation_router.router, prefix="/api", tags=["invitations"])
app.include_router(realtime_router.router, prefix="/api", tags=["realtime"])

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.exception_handler(RequestValidationError)
async def validation_error(_request, error):
    safe = [{"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": safe})

@app.exception_handler(IntegrityError)
async def integrity_error(_request, _error):
    return JSONResponse(status_code=409, content={"detail": {"code": "DATABASE_CONFLICT", "message": "Data changed or violates a constraint. Reload and try again."}})

@app.exception_handler(OperationalError)
async def database_error(_request, error):
    if "locked" in str(error.orig).lower() or "deadlock" in str(error.orig).lower():
        return JSONResponse(status_code=409, content={"detail": {"code": "CONCURRENT_CHANGE", "message": "Another change is in progress. Reload and try again."}})
    logger.error("Database operation failed (%s)", type(error.orig).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@app.exception_handler(Exception)
async def unexpected_error(request: Request, error):
    logger.error("Unhandled %s on %s %s", type(error).__name__, request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
