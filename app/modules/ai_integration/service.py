"""AI integration service (Phase 8) — provider-agnostic, explain-only.

Architectural constraint: the deterministic engine owns truth; the LLM only
explains it. ``generate_explanation`` receives pre-computed context (never raw
observations), is never allowed to modify evidence or attribution, and falls
back to a template explanation if the provider is unavailable.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.core.security import decrypt_jsonb, encrypt_jsonb
from app.modules.ai_integration.models import AiProvider
from app.modules.ai_integration.repository import AiProviderRepository
from app.modules.ai_integration.schemas import (
    AiProviderCreateRequest,
    AiProviderResponse,
    AiProviderUpdateRequest,
)

logger = logging.getLogger(__name__)

_GROUNDING_INSTRUCTIONS = (
    "You are an analyst writing a summary of externally-verified incident evidence. "
    "Only state facts supported by the provided context. Do not invent measurements, "
    "do not assign fault beyond the pre-computed confidence score, and do not modify "
    "any evidence. If the context is insufficient, say so."
)


class AiProviderAdapter:
    """Builds provider-specific request payloads from a generic request."""

    @staticmethod
    def build_request(
        provider_type: str,
        *,
        endpoint_url: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        ptype = provider_type.lower()
        if ptype == "anthropic":
            return {
                "method": "POST",
                "url": endpoint_url.rstrip("/") + "/v1/messages",
                "headers": {
                    "x-api-key": "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                "json": {
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            }
        if ptype == "google":
            return {
                "method": "POST",
                "url": endpoint_url.rstrip("/"),
                "headers": {"x-goog-api-key": "", "content-type": "application/json"},
                "json": {
                    "contents": [{"parts": [{"text": system_prompt + "\n\n" + user_prompt}]}]
                },
            }
        # openai_compatible and mistral use the chat/completions shape.
        base = endpoint_url.rstrip("/")
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        return {
            "method": "POST",
            "url": url,
            "headers": {"authorization": "Bearer ", "content-type": "application/json"},
            "json": {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        }


class AiService:
    def __init__(
        self, repository: AiProviderRepository = AiProviderRepository()
    ) -> None:
        self.repository = repository

    # -- provider config management ------------------------------------------

    async def list_providers(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[AiProviderResponse]:
        providers = await self.repository.list_for_org(session, org_id)
        return [AiProviderResponse.model_validate(p) for p in providers]

    async def get_provider(
        self, session: AsyncSession, org_id: uuid.UUID, provider_id: uuid.UUID
    ) -> AiProviderResponse:
        provider = await self.repository.get_by_id(session, org_id, provider_id)
        if not provider:
            raise ResourceNotFoundException("AI provider not found")
        return AiProviderResponse.model_validate(provider)

    async def create_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: AiProviderCreateRequest,
    ) -> AiProviderResponse:
        provider = await self.repository.create(
            session=session,
            org_id=org_id,
            name=request.name,
            provider_type=request.provider_type,
            endpoint_url=request.endpoint_url,
            encrypted_api_key=encrypt_jsonb({"key": request.api_key}) or "",
            model_name=request.model_name,
            is_default=request.is_default,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            enabled=request.enabled,
        )
        return AiProviderResponse.model_validate(provider)

    async def update_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        provider_id: uuid.UUID,
        request: AiProviderUpdateRequest,
    ) -> AiProviderResponse:
        provider = await self.repository.get_by_id(session, org_id, provider_id)
        if not provider:
            raise ResourceNotFoundException("AI provider not found")

        updates: dict[str, Any] = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.provider_type is not None:
            updates["provider_type"] = request.provider_type
        if request.endpoint_url is not None:
            updates["endpoint_url"] = request.endpoint_url
        if request.api_key is not None:
            updates["encrypted_api_key"] = encrypt_jsonb({"key": request.api_key}) or ""
        if request.model_name is not None:
            updates["model_name"] = request.model_name
        if request.is_default is not None:
            updates["is_default"] = request.is_default
        if request.max_tokens is not None:
            updates["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            updates["temperature"] = request.temperature
        if request.enabled is not None:
            updates["enabled"] = request.enabled

        updated = await self.repository.update(session, provider, **updates)
        return AiProviderResponse.model_validate(updated)

    async def delete_provider(
        self, session: AsyncSession, org_id: uuid.UUID, provider_id: uuid.UUID
    ) -> None:
        provider = await self.repository.get_by_id(session, org_id, provider_id)
        if not provider:
            raise ResourceNotFoundException("AI provider not found")
        await self.repository.delete(session, provider)

    # -- explain-only generation ----------------------------------------------

    async def generate_explanation(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        context: dict[str, Any],
        instruction: str,
    ) -> str:
        provider = await self.repository.get_default(session, org_id)
        if not provider:
            return self._template_explanation(context)

        decrypted = decrypt_jsonb(provider.encrypted_api_key) or {}
        api_key = decrypted.get("key", "")

        user_prompt = (
            f"Context (pre-computed evidence):\n{json.dumps(context, default=str)}\n\n"
            f"Instruction: {instruction}"
        )
        request_data = AiProviderAdapter.build_request(
            provider.provider_type,
            endpoint_url=provider.endpoint_url,
            model_name=provider.model_name,
            system_prompt=_GROUNDING_INSTRUCTIONS,
            user_prompt=user_prompt,
            max_tokens=provider.max_tokens,
            temperature=provider.temperature,
        )

        # Inject the decrypted key into the provider-specific header.
        headers = request_data["headers"]
        if "authorization" in headers:
            headers["authorization"] = f"Bearer {api_key}"
        elif "x-api-key" in headers:
            headers["x-api-key"] = api_key
        elif "x-goog-api-key" in headers:
            headers["x-goog-api-key"] = api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    request_data["method"],
                    request_data["url"],
                    headers=headers,
                    json=request_data["json"],
                )
                resp.raise_for_status()
                return self._extract_text(provider.provider_type, resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI generation failed, using template fallback: %s", exc)
            return self._template_explanation(context)

    @staticmethod
    def _extract_text(provider_type: str, payload: dict[str, Any]) -> str:
        if provider_type.lower() == "google":
            try:
                return payload["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                return str(payload)
        try:
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return str(payload)

    @staticmethod
    def _template_explanation(context: dict[str, Any]) -> str:
        confidence = context.get("confidence_score")
        dep = context.get("dependency_id") or context.get("dependency_name") or "the monitored dependency"
        return (
            "AI-generated explanation unavailable. Deterministic attribution "
            f"identifies {dep} with confidence {confidence if confidence is not None else 'N/A'} "
            "(methodology v1.0)."
        )


ai_service = AiService()
