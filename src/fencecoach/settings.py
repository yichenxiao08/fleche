from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    coach_core: Literal["old", "new"] = "new"
    fencecoach_fast_reply_tokens: int = 112
    fencecoach_examples_dir: Path = Path("examples/video")
    fencecoach_seed_examples: bool = False
    fencecoach_phoenix_endpoint: str = ""
    fencecoach_input_usd_per_million: float | None = None
    fencecoach_output_usd_per_million: float | None = None
    fencecoach_automatic_training: bool = False
    fencecoach_chat_provider: str = "gemini"
    fencecoach_provider_cooldown_seconds: float = 60
    fencecoach_local_timeout_seconds: float = 20
    fencecoach_verified_dialogue: bool = False
    fencecoach_local_fallback: bool = True
    fencecoach_coaching_worker: bool = True
    fencecoach_coaching_concurrency: int = 1
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:3b"
    groq_api_key: SecretStr = SecretStr("")
    groq_chat_model: str = "qwen/qwen3.8-27b"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.8-flash"
    gemini_request_timeout_seconds: float = 12
    gemini_force_ipv4: bool = True
    fencecoach_database_url: str = ""
    fencecoach_worker_concurrency: int = 1
    fencecoach_queue_limit: int = 100
    fencecoach_gesture_model: Path = Path("models/gestures.json")
    fencecoach_activity_model: Path = Path("models/activity.json")
    fencecoach_s3_bucket: str = ""
    fencecoach_s3_prefix: str = "fencecoach"
    fencecoach_s3_endpoint: str = ""
    aws_region: str = "us-east-1"
    bedrock_chat_model_id: str = ""
    bedrock_embedding_model_id: str = ""
    fencecoach_knowledge_dir: Path = Path("knowledge")
    fencecoach_db_path: Path = Path("data/fencecoach.sqlite3")
    fencecoach_video_dir: Path = Path("data/videos")
    fencecoach_pose_model: Path = Path("models/pose_landmarker_full.task")
    fencecoach_video_worker: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
