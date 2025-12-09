from __future__ import annotations

from .audio import AudioCaptureService
from .config import get_settings
from .controller import AssistantController
from .gui import AssistantGUI
from .openai_client import OpenAIAudioClient, OpenAIIntentClient
from .zotero_client import ZoteroClient


def main() -> None:
    settings = get_settings()
    audio_capture = AudioCaptureService(
        sample_rate=settings.audio_sample_rate,
        channels=settings.audio_channels,
        input_device=settings.audio_input_device,
        default_duration=settings.audio_default_duration,
    )
    openai_client = OpenAIAudioClient(settings)
    intent_parser = OpenAIIntentClient(settings)
    zotero_client = ZoteroClient(settings)
    controller = AssistantController(
        settings=settings,
        audio_capture=audio_capture,
        openai_client=openai_client,
        zotero_client=zotero_client,
        intent_parser=intent_parser,
    )
    gui = AssistantGUI(controller)
    gui.run()


if __name__ == "__main__":
    main()
