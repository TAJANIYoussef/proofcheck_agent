"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Ollama
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    model_name: str = Field(default="gpt-oss:20b", alias="MODEL_NAME")

    # Verification behaviour
    max_cove_rounds: int = Field(default=2, alias="MAX_COVE_ROUNDS", ge=1, le=5)

    # Storage
    session_dir: Path = Field(default=Path("sessions"), alias="SESSION_DIR")

    # Reporting
    pdf_export_enabled: bool = Field(default=True, alias="PDF_EXPORT_ENABLED")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    @property
    def openai_base_url(self) -> str:
        """OpenAI-compatible endpoint served by Ollama."""
        return f"{self.ollama_host.rstrip('/')}/v1"

    def configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


# Module-level singleton — import this everywhere.
settings = Settings()
