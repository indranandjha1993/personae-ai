"""Provider construction.

Selection happens once at startup so a misconfigured deployment fails at boot
with a precise message, rather than on the first user utterance.
"""

from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.providers.mock import MockLlm, MockStt, MockTts
from personae.settings import Settings


def build_stt(settings: Settings) -> SttProvider:
    if settings.stt_mode == "mock":
        return MockStt()
    from personae.providers.deepgram import DeepgramStt

    return DeepgramStt(
        api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
        model=settings.stt_model,
        endpointing_ms=settings.endpointing_ms,
        utterance_end_ms=settings.utterance_end_ms,
    )


def build_tts(settings: Settings) -> TtsProvider:
    if settings.tts_mode == "mock":
        return MockTts()
    from personae.providers.deepgram import DeepgramTts

    return DeepgramTts(
        api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
        voice=settings.tts_voice,
    )


def build_llm(settings: Settings) -> LlmProvider:
    if settings.llm_mode == "mock":
        return MockLlm()
    from personae.providers.openai_compat import OpenAiCompatibleLlm

    # Reported together: being told about one missing value, fixing it, and
    # then being told about the next is a poor first-run experience.
    _require_all(
        (settings.llm_api_key, "LLM_API_KEY"),
        (settings.llm_base_url, "LLM_BASE_URL"),
    )
    return OpenAiCompatibleLlm(
        base_url=settings.llm_base_url or "",
        api_key=settings.llm_api_key or "",
        model=settings.llm_model,
    )


def _require(value: str | None, name: str) -> str:
    """Return a configured value, or explain precisely what is missing."""
    _require_all((value, name))
    return value or ""


def _require_all(*required: tuple[str | None, str]) -> None:
    missing = [name for value, name in required if not value]
    if missing:
        names = ", ".join(f"PERSONAE_{name}" for name in missing)
        raise ValueError(f"{names} must be set when the matching provider mode is 'live'")
