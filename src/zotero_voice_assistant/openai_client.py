from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel

from .config import AppSettings


class OpenAIAudioClient:
    """Thin wrapper around the OpenAI audio transcription endpoint."""

    def __init__(self, settings: AppSettings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._language = settings.openai_transcription_language

    def transcribe_file(self, audio_file: Path, prompt: Optional[str] = None) -> str:
        if not audio_file.exists():
            raise FileNotFoundError(audio_file)
        with audio_file.open("rb") as handle:
            request_kwargs = {
                "model": self._model,
                "file": handle,
                "prompt": prompt,
                "response_format": "text",
            }
            if self._language:
                request_kwargs["language"] = self._language
            response = self._client.audio.transcriptions.create(**request_kwargs)
        return response


@dataclass
class SearchIntent:
    raw_query: str
    search_terms: str
    author: Optional[str] = None
    title: Optional[str] = None
    year: Optional[str] = None
    confidence: float = 0.0

    @property
    def has_structured_filters(self) -> bool:
        return any(value for value in (self.author, self.title, self.year))


class IntentPayload(BaseModel):
    search_terms: Optional[str] = None
    author: Optional[str] = None
    title: Optional[str] = None
    year: Optional[str] = None
    confidence: float = 0.0


class OpenAIIntentClient:
    """Uses a text model to convert natural language into structured Zotero filters."""

    _SYSTEM_PROMPT = (
        "You translate informal user requests about Zotero citations into structured JSON. "
        "Always respond with the keys: search_terms, author, title, year, confidence. "
        "Use null for any field that is not specified. "
        "search_terms should be a short keyword query if no precise filters are found. "
        "If the user references an author (e.g., 'papers by Zimmerman'), set author to that surname. "
        "When they mention a title, place it in title. Year should be a four-digit string when present."
    )

    def __init__(self, settings: AppSettings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_text_model

    def parse(self, query: str) -> SearchIntent:
        response = self._client.responses.parse(
            model=self._model,
            temperature=0,
            text_format=IntentPayload,
            input=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"User request: {query}",
                },
            ],
        )
        payload: Optional[IntentPayload] = getattr(response, "output_parsed", None)
        if payload is None:
            raise ValueError("Intent parser did not return structured data")
        search_terms = payload.search_terms or query
        return SearchIntent(
            raw_query=query.strip(),
            search_terms=search_terms.strip(),
            author=self._clean_field(payload.author),
            title=self._clean_field(payload.title),
            year=self._clean_field(payload.year),
            confidence=float(payload.confidence or 0.0),
        )

    @staticmethod
    def _clean_field(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None
