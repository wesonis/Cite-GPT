from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppSettings:
    openai_api_key: str
    openai_model: str = "gpt-4o-mini-transcribe"
    openai_text_model: str = "gpt-4o-mini"
    openai_transcription_language: str = "en"
    zotero_api_key: str = ""
    zotero_library_id: str = ""
    zotero_library_type: str = "user"
    zotero_use_local: bool = False
    activation_keywords: List[str] = field(
        default_factory=lambda: ["citation assistant", "find paper"]
    )
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_input_device: Optional[str] = None
    audio_default_duration: int = 5


def get_settings() -> AppSettings:
    return AppSettings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_AUDIO_MODEL", "gpt-4o-mini-transcribe"),
        openai_text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini"),
        openai_transcription_language=os.getenv("OPENAI_TRANSCRIPTION_LANGUAGE", "en"),
        zotero_api_key=os.getenv("ZOTERO_API_KEY", ""),
        zotero_library_id=os.getenv("ZOTERO_LIBRARY_ID", ""),
        zotero_library_type=os.getenv("ZOTERO_LIBRARY_TYPE", "user"),
        zotero_use_local=_env_flag(
            "ZOTERO_USE_LOCAL", fallback_names=["ZOTERO_LOCAL_BOOL"], default=False
        ),
        audio_sample_rate=_env_int("AUDIO_SAMPLE_RATE", 16000),
        audio_channels=_env_int("AUDIO_CHANNELS", 1),
        audio_input_device=_env_optional_str("AUDIO_INPUT_DEVICE"),
        audio_default_duration=_env_int("AUDIO_DEFAULT_DURATION", 5),
    )


def _env_flag(name: str, fallback_names: Optional[List[str]] = None, default: bool = False) -> bool:
    names = [name]
    if fallback_names:
        names.extend(fallback_names)
    for candidate in names:
        value = os.getenv(candidate)
        if value is None:
            continue
        value_lower = value.strip().lower()
        if value_lower in {"1", "true", "yes", "on"}:
            return True
        if value_lower in {"0", "false", "no", "off"}:
            return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_optional_str(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value
