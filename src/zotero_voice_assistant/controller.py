from __future__ import annotations

import threading
from contextlib import suppress
from pathlib import Path
from typing import Callable, List, Optional

from .audio import AudioCaptureService, CapturedAudio, RecordingCancelled
from .config import AppSettings
from .openai_client import OpenAIAudioClient, OpenAIIntentClient, SearchIntent
from .zotero_client import ZoteroClient

StatusCallback = Callable[[bool], None]
LogCallback = Callable[[str], None]
TranscriptCallback = Callable[[str], None]
RecordingStateCallback = Callable[[bool], None]
ResultsCallback = Callable[[List[dict]], None]
RetryPrompt = Callable[[bool], str]


class AssistantController:
    def __init__(
        self,
        settings: AppSettings,
        audio_capture: AudioCaptureService,
        openai_client: OpenAIAudioClient,
        zotero_client: ZoteroClient,
        intent_parser: Optional[OpenAIIntentClient] = None,
    ) -> None:
        self._settings = settings
        self._audio_capture = audio_capture
        self._openai_client = openai_client
        self._zotero_client = zotero_client
        self._intent_parser = intent_parser
        self._listening = False
        self._listeners: List[StatusCallback] = []
        self._loggers: List[LogCallback] = []
        self._transcript_listeners: List[TranscriptCallback] = []
        self._recording_state_listeners: List[RecordingStateCallback] = []
        self._results_listeners: List[ResultsCallback] = []
        self._retry_prompt: Optional[RetryPrompt] = None
        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_results: List[dict] = []

    def add_status_listener(self, callback: StatusCallback) -> None:
        self._listeners.append(callback)

    def add_log_listener(self, callback: LogCallback) -> None:
        self._loggers.append(callback)

    def add_transcript_listener(self, callback: TranscriptCallback) -> None:
        self._transcript_listeners.append(callback)

    def add_recording_listener(self, callback: RecordingStateCallback) -> None:
        self._recording_state_listeners.append(callback)

    def add_results_listener(self, callback: ResultsCallback) -> None:
        self._results_listeners.append(callback)

    def set_retry_prompt_handler(self, handler: RetryPrompt) -> None:
        self._retry_prompt = handler

    def start(self) -> None:
        if self._listening:
            return
        self._stop_event = threading.Event()
        self._listening = True
        self._push_status(True)
        self._worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self._worker.start()
        self._log(
            f"Assistant activated (recording up to {self._settings.audio_default_duration} seconds)"
        )
        self._log(f"Zotero target: {self._zotero_client.describe_target()}")
        self._push_results([])

    def stop(self) -> None:
        if not self._listening:
            return
        self._stop_event.set()
        self._log("Stopping current run...")

    def resolve_item_location(self, item: dict) -> Optional[str]:
        title = item.get("data", {}).get("title", "Untitled")
        location = self._zotero_client.get_attachment_or_url(item)
        if location:
            self._log(f"Resolved location for '{title}' -> {location}")
        else:
            self._log(f"No attachment or URL available for '{title}'")
        return location

    def _run_pipeline(self) -> None:
        snippet: Optional[Path] = None
        try:
            self._push_recording_state(True)
            self._log(
                f"Recording audio snippet for up to {self._settings.audio_default_duration} seconds..."
            )
            captured: CapturedAudio = self._audio_capture.record_snippet(
                duration_seconds=self._settings.audio_default_duration,
                stop_event=self._stop_event,
            )
            snippet = captured.path
            self._push_recording_state(False)

            self._log("Transcribing audio with OpenAI...")
            transcript = self._openai_client.transcribe_file(snippet)
            pretty_transcript = transcript.strip() or "[empty]"
            self._log(f"Raw audio transcription: {pretty_transcript}")
            self._push_transcript(transcript)
            self._handle_transcript(transcript)
        except RecordingCancelled:
            self._log("Recording cancelled")
        except NotImplementedError as exc:
            self._log(str(exc))
        except Exception as exc:
            self._log(f"Pipeline error: {exc}")
        finally:
            if snippet is not None:
                with suppress(FileNotFoundError, PermissionError):
                    snippet.unlink(missing_ok=True)
            self._cleanup_after_run()

    def _cleanup_after_run(self) -> None:
        self._push_recording_state(False)
        self._stop_event.set()
        self._listening = False
        self._push_status(False)
        self._log("Assistant stopped")

    def _handle_transcript(self, transcript: str) -> None:
        query = self._extract_query(transcript)
        if not query:
            self._log("Nothing transcribed; press 'Record Clip' to try again")
            return

        intent: Optional[SearchIntent] = None
        if self._intent_parser:
            self._log(f"Parsing input with {self._settings.openai_text_model}...")
            try:
                intent = self._intent_parser.parse(query)
                self._log(self._summarize_intent(intent))
            except Exception as exc:
                self._log(f"Intent parsing failed: {exc}")

        self._log("Searching Zotero...")
        matches = self._run_search(intent, query)
        expanded = False
        while not matches:
            self._log("No Zotero items matched")
            choice = self._prompt_retry(expand_allowed=not expanded)
            if choice == "expand" and not expanded:
                expanded = True
                self._log("Expanding search across all fields...")
                matches = self._run_search(intent, query, expand=True)
                continue
            if choice == "retry":
                self._log("User chose to record another clip")
                return
            self._log("User cancelled the search")
            return

        self._push_results(matches)
        self._log(f"{len(matches)} item(s) found. Select from display.")

    def _extract_query(self, transcript: str) -> Optional[str]:
        stripped = transcript.strip()
        if not stripped:
            return None
        lowered = stripped.lower()
        for keyword in self._settings.activation_keywords:
            if keyword and keyword in lowered:
                idx = lowered.index(keyword) + len(keyword)
                remainder = stripped[idx:].strip().strip(",.:")
                return remainder or stripped
        return stripped

    def _push_status(self, active: bool) -> None:
        for callback in self._listeners:
            callback(active)

    def _log(self, message: str) -> None:
        for logger in self._loggers:
            logger(message)

    def _push_transcript(self, transcript: str) -> None:
        for callback in self._transcript_listeners:
            callback(transcript)

    def _push_recording_state(self, active: bool) -> None:
        for callback in self._recording_state_listeners:
            callback(active)

    def _push_results(self, items: List[dict]) -> None:
        self._latest_results = items
        for callback in self._results_listeners:
            callback(items)

    def _prompt_retry(self, expand_allowed: bool) -> str:
        if not self._retry_prompt:
            return "expand" if expand_allowed else "retry"
        return self._retry_prompt(expand_allowed)

    def _summarize_intent(self, intent: SearchIntent) -> str:
        labels: List[str] = []
        values: List[str] = []
        if intent.author:
            labels.append("author")
            values.append(intent.author)
        if intent.title:
            labels.append("title")
            values.append(intent.title)
        if intent.year:
            labels.append("year")
            values.append(intent.year)
        if labels:
            if len(labels) == 1:
                field_text = labels[0]
            elif len(labels) == 2:
                field_text = " and ".join(labels)
            else:
                field_text = ", ".join(labels[:-1]) + f", and {labels[-1]}"
            suffix = "field" if len(labels) == 1 else "fields"
            return f"Inputs for {field_text} {suffix} detected: {', '.join(values)}."
        return f"Keyword search terms detected: {intent.search_terms}"

    def _run_search(
        self,
        intent: Optional[SearchIntent],
        fallback_query: str,
        *,
        expand: bool = False,
    ) -> List[dict]:
        try:
            if intent and intent.has_structured_filters and not expand:
                self._log("Running Zotero fielded search with detected filters")
                return self._zotero_client.search_by_fields(
                    author=intent.author,
                    title=intent.title,
                    year=intent.year,
                )
            search_terms = (intent.search_terms if intent else fallback_query) or fallback_query
            qmode = "everything" if expand else None
            scope = "expanded" if expand else "direct"
            self._log(f"Keyword search ({scope}): {search_terms}")
            return self._zotero_client.search_items(search_terms, qmode=qmode)
        except Exception as exc:
            self._log(f"Zotero search failed: {exc}")
            return []

    @property
    def is_listening(self) -> bool:
        return self._listening
