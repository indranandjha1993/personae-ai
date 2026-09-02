"""Provider construction.

Selection happens once at startup so a misconfigured deployment fails at boot
with a precise message, rather than on the first user utterance.
"""

from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.providers.mock import MockLlm, MockStt, MockTts
from personae.settings import Settings


def build_stt(settings: Settings) -> SttProvider:
    """Live when a key is configured, a fake otherwise.

    Selection follows the credentials rather than an explicit switch: a mode
    that disagrees with the keys present is a confusing way to fail.
    """
    if not settings.deepgram_api_key:
        return MockStt()

    # Flux is a different endpoint with its own turn detection, so the model
    # name picks the client rather than being passed to a common one.
    if settings.stt_model.startswith("flux-"):
        from personae.providers.flux import FluxStt

        return FluxStt(
            api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
            model=settings.stt_model,
            eot_threshold=settings.eot_threshold,
            eot_timeout_ms=settings.eot_timeout_ms,
        )

    from personae.providers.deepgram import DeepgramStt

    return DeepgramStt(
        api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
        model=settings.stt_model,
        language=settings.stt_language,
        endpointing_ms=settings.endpointing_ms,
        utterance_end_ms=settings.utterance_end_ms,
    )


def build_tts(settings: Settings) -> TtsProvider:
    if not settings.deepgram_api_key:
        return MockTts()

    if settings.tts_voice.startswith("flux-"):
        from personae.providers.flux import FluxTts

        return FluxTts(
            api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
            voice=settings.tts_voice,
        )

    from personae.providers.deepgram import DeepgramTts

    return DeepgramTts(
        api_key=_require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
        voice=settings.tts_voice,
    )


def build_llm(settings: Settings) -> LlmProvider:
    if not settings.llm_api_key:
        return MockLlm()

    # A key with no endpoint is half-configured; say so rather than falling
    # back to a fake and leaving someone wondering why nothing is live.
    _require_all((settings.llm_base_url, "LLM_BASE_URL"))

    if settings.llm_wire == "anthropic":
        from personae.providers.anthropic_compat import AnthropicCompatibleLlm

        return AnthropicCompatibleLlm(
            base_url=settings.llm_base_url or "",
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            vision_model=settings.vision_model,
        )

    from personae.providers.openai_compat import OpenAiCompatibleLlm

    return OpenAiCompatibleLlm(
        base_url=settings.llm_base_url or "",
        api_key=settings.llm_api_key,
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
