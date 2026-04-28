"""LLM provider factory using LangChain wrappers.

Creates the appropriate LangChain chat model and embeddings instances
based on application settings. All LLM access MUST go through these
factory functions — never use raw OpenAI/Anthropic clients.
"""

import re

from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config.settings import Settings


# OpenAI reasoning models (o1*, o3*, o4*) reject any temperature other than
# the default 1. Detect them so we don't pass `temperature` at all.
_REASONING_MODEL_RE = re.compile(r"^o\d", re.IGNORECASE)


def _is_reasoning_model(model_name: str) -> bool:
    return bool(_REASONING_MODEL_RE.match(model_name or ""))


def get_llm(settings: Settings) -> BaseChatModel:
    """Get the configured LLM provider via LangChain.

    Factory function that returns the appropriate LangChain chat model
    based on the configured provider (OpenAI or Anthropic).

    Args:
        settings: Application settings with provider configuration.

    Returns:
        A LangChain BaseChatModel instance ready for chain composition.

    Raises:
        ValueError: If the configured provider is not supported.
    """
    if settings.llm_provider == "openai":
        kwargs: dict = {
            "model": settings.openai_model,
            "max_completion_tokens": settings.llm_max_tokens,
            "api_key": settings.openai_api_key.get_secret_value(),
        }
        # Reasoning models (o1/o3/o4) only accept the default temperature.
        # Passing anything (even `1`) triggers a 400; safest is to omit it.
        if not _is_reasoning_model(settings.openai_model):
            kwargs["temperature"] = settings.llm_temperature
        return ChatOpenAI(**kwargs)  # type: ignore[arg-type]
    elif settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=settings.anthropic_model,  # type: ignore[arg-type]
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.anthropic_api_key.get_secret_value(),  # type: ignore[arg-type]
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def get_embeddings(settings: Settings) -> Embeddings:
    """Get the configured embeddings model via LangChain.

    Currently uses OpenAI embeddings. The OpenAI API key is required
    regardless of the selected LLM provider.

    Args:
        settings: Application settings with embedding configuration.

    Returns:
        A LangChain Embeddings instance for generating vectors.
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key.get_secret_value(),  # type: ignore[arg-type]
    )
