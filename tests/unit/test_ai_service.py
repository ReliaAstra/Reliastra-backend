import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.ai_integration.service import AiService, AiProviderAdapter


def test_build_request_openai_compatible():
    req = AiProviderAdapter.build_request(
        "openai_compatible",
        endpoint_url="https://api.example.com/v1",
        model_name="gpt-4",
        system_prompt="sys",
        user_prompt="user",
        max_tokens=100,
        temperature=0.3,
    )
    assert req["json"]["model"] == "gpt-4"
    assert req["headers"]["authorization"].startswith("Bearer")
    assert req["url"].endswith("/chat/completions")


def test_build_request_anthropic():
    req = AiProviderAdapter.build_request(
        "anthropic",
        endpoint_url="https://api.anthropic.com",
        model_name="claude-3-sonnet",
        system_prompt="sys",
        user_prompt="user",
        max_tokens=100,
        temperature=0.3,
    )
    assert "x-api-key" in req["headers"]
    assert req["url"].endswith("/v1/messages")


@pytest.mark.asyncio
async def test_generate_explanation_falls_back_without_provider():
    repo = MagicMock()
    repo.get_default = AsyncMock(return_value=None)
    service = AiService(repository=repo)
    session = AsyncMock()
    result = await service.generate_explanation(
        session,
        uuid.uuid4(),
        {"confidence_score": 0.85},
        "Explain in plain language",
    )
    assert "AI-generated explanation unavailable" in result
