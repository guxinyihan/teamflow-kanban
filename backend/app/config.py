"""Implemented configuration only; signing secrets come from the operator."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def origins():
    value = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    result = json.loads(value) if value.startswith("[") else value.split(",")
    return [origin.strip().rstrip("/") for origin in result if origin.strip()]

@dataclass
class Settings:
    DATABASE_URL: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./kanban.db"))
    JWT_SECRET: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    ACCESS_TOKEN_MINUTES: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_MINUTES", "30")))
    FRONTEND_ORIGINS: list[str] = field(default_factory=origins)
    UPLOAD_DIR: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", "private_uploads")).resolve())
    MAX_UPLOAD_BYTES: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))))
    INVITE_HOURS: int = field(default_factory=lambda: int(os.getenv("INVITE_HOURS", "48")))

    def validate_runtime(self):
        if len(self.JWT_SECRET.encode()) < 32:
            raise RuntimeError("Set JWT_SECRET to a random secret of at least 32 bytes")
        if not 1 <= self.ACCESS_TOKEN_MINUTES <= 1440:
            raise RuntimeError("ACCESS_TOKEN_MINUTES must be between 1 and 1440")
        if self.MAX_UPLOAD_BYTES < 1 or self.INVITE_HOURS < 1:
            raise RuntimeError("Upload and invitation limits must be positive")
        if not self.FRONTEND_ORIGINS or "*" in self.FRONTEND_ORIGINS:
            raise RuntimeError("FRONTEND_ORIGINS must list explicit origins")

settings = Settings()
