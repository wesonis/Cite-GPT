from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Union
import time

try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
except ImportError:  # pragma: no cover - handled at runtime for CLI scenarios
    np = None  # type: ignore
    sd = None  # type: ignore
    sf = None  # type: ignore


DeviceSpecifier = Union[int, str, None]


@dataclass
class CapturedAudio:
    path: Path
    level: float


class RecordingCancelled(Exception):
    """Raised when the user stops recording before completion."""


class AudioCaptureService:
    """Records short microphone snippets to temporary WAV files."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        input_device: DeviceSpecifier = None,
        default_duration: int = 5,
    ) -> None:
        if sd is None or sf is None or np is None:  # pragma: no cover - import guard
            raise RuntimeError(
                "sounddevice and soundfile are required; reinstall the project dependencies"
            )
        self._sample_rate = sample_rate
        self._channels = channels
        self._input_device = self._coerce_device(input_device)
        self._default_duration = max(1, default_duration)
        self._dtype = "float32"
        self._block_size = max(int(self._sample_rate * 0.1), 512)

    def record_snippet(
        self,
        duration_seconds: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> CapturedAudio:
        duration = duration_seconds or self._default_duration
        if duration <= 0:
            raise ValueError("duration_seconds must be positive")
        total_frames = int(duration * self._sample_rate)
        stop_event = stop_event or threading.Event()
        if stop_event.is_set():
            raise RecordingCancelled

        try:
            buffer = sd.rec(
                total_frames,
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=self._dtype,
                device=self._input_device,
            )
            start_time = time.monotonic()
            poll_ms = 50
            while True:
                if stop_event.is_set():
                    sd.stop()
                    sd.wait()
                    raise RecordingCancelled
                elapsed = time.monotonic() - start_time
                if elapsed >= duration:
                    break
                sd.sleep(poll_ms)
            sd.wait()
        except RecordingCancelled:
            raise
        except Exception as exc:  # pragma: no cover - hardware dependent
            sd.stop()
            raise RuntimeError(
                "Audio capture failed; check your microphone permissions and device"
            ) from exc

        recording = np.copy(buffer)
        peak_level = float(np.max(np.abs(recording))) if recording.size else 0.0
        normalized = max(0.0, min(1.0, peak_level))

        with NamedTemporaryFile(prefix="zva_", suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, recording, self._sample_rate)
            return CapturedAudio(Path(tmp.name), normalized)

    def _coerce_device(self, device: DeviceSpecifier) -> DeviceSpecifier:
        if isinstance(device, str):
            stripped = device.strip()
            if stripped == "":
                return None
            if stripped.isdigit():
                return int(stripped)
            return stripped
        if isinstance(device, int):
            return device
        return None
