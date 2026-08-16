import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.security import decrypt_jsonb, encrypt_jsonb
from app.core.ssrf_protection import validate_outbound_url
from app.modules.ai_integration.models import AIProvider
from app.modules.ai_integration.repository import AIProviderRepository
from app.modules.ai_integration.schemas import (
    AIProviderCreateRequest,
    AIProviderResponse,
    AIProviderUpdateRequest,
)

logger = logging.getLogger(__name__)


class AIService:
    def __init__(
        self, repository: AIProviderRepository = AIProviderRepository()
    ) -> None:
        self.repository = repository

    @staticmethod
    def _response(provider: AIProvider) -> AIProviderResponse:
        data = {
            key: getattr(provider, key)
            for key in (
                "id",
                "organization_id",
                "name",
                "provider_type",
                "endpoint_url",
                "model_name",
                "is_default",
                "max_tokens",
                "temperature",
                "enabled",
                "created_at",
                "updated_at",
            )
        }
        data["has_api_key"] = bool(provider.encrypted_api_key)
        return AIProviderResponse.model_validate(data)

    async def list_providers(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[AIProviderResponse]:
        providers = await self.repository.list_for_org(session, org_id)
        return [self._response(provider) for provider in providers]

    async def create_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: AIProviderCreateRequest,
    ) -> AIProviderResponse:
        try:
            validate_outbound_url(request.endpoint_url)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        if request.is_default:
            await self.repository.clear_defaults(session, org_id)
        encrypted = (
            encrypt_jsonb({"api_key": request.api_key.get_secret_value()})
            if request.api_key
            else None
        )
        provider = await self.repository.create(
            session,
            organization_id=org_id,
            name=request.name,
            provider_type=request.provider_type,
            endpoint_url=request.endpoint_url,
            encrypted_api_key=encrypted,
            model_name=request.model_name,
            is_default=request.is_default,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            enabled=request.enabled,
        )
        return self._response(provider)

    async def update_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        provider_id: uuid.UUID,
        request: AIProviderUpdateRequest,
    ) -> AIProviderResponse:
        provider = await self.repository.get_by_id(session, provider_id)
        if not provider or provider.organization_id != org_id:
            raise ResourceNotFoundException("AI provider not found")
        values = request.model_dump(
            exclude_unset=True, exclude={"api_key"}
        )
        if request.endpoint_url is not None:
            try:
                validate_outbound_url(request.endpoint_url)
            except ValueError as exc:
                raise ValidationException(str(exc)) from exc
        if "api_key" in request.model_fields_set:
            values["encrypted_api_key"] = (
                encrypt_jsonb(
                    {"api_key": request.api_key.get_secret_value()}
                )
                if request.api_key
                else None
            )
        if request.is_default is True:
            await self.repository.clear_defaults(
                session, org_id, exclude_id=provider.id
            )
        updated = await self.repository.update(session, provider, **values)
        return self._response(updated)

    async def delete_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        provider_id: uuid.UUID,
    ) -> None:
        provider = await self.repository.get_by_id(session, provider_id)
        if not provider or provider.organization_id != org_id:
            raise ResourceNotFoundException("AI provider not found")
        await self.repository.delete(session, provider)

    async def generate_explanation(
        self,
        context: dict[str, Any],
        instruction: str,
        session: AsyncSession,
        org_id: uuid.UUID,
    ) -> str | None:
        """Explain pre-computed facts; never create or alter attribution truth."""
        provider = await self.repository.get_active_default(session, org_id)
        if not provider:
            return None
        key_data = decrypt_jsonb(provider.encrypted_api_key)
        api_key = key_data.get("api_key") if key_data else None
        if not api_key:
            return None

        prompt = (
            "You are a technical evidence explainer. Explain only the supplied "
            "pre-computed evidence. Do not invent measurements, conclusions, or "
            "facts. Do not alter the attribution result or confidence score.\n\n"
            f"Instruction: {instruction}\n\nEvidence Data:\n{context}\n\n"
            "Use clear language and state that this is an AI-generated explanation."
        )
        try:
            validate_outbound_url(provider.endpoint_url)
            headers, payload = self._request(provider, str(api_key), prompt)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    provider.endpoint_url, headers=headers, json=payload
                )
                response.raise_for_status()
                return self._extract(provider.provider_type, response.json())
        except Exception as exc:
            logger.warning("AI generation failed: %s", exc)
            return None

    @staticmethod
    def _request(
        provider: AIProvider, api_key: str, prompt: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if provider.provider_type == "anthropic":
            headers.update(
                {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            )
            payload = {
                "model": provider.model_name,
                "max_tokens": provider.max_tokens,
                "temperature": provider.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif provider.provider_type == "google":
            headers["x-goog-api-key"] = api_key
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": provider.max_tokens,
                    "temperature": provider.temperature,
                },
            }
        else:
            headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": provider.model_name,
                "max_tokens": provider.max_tokens,
                "temperature": provider.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
        return headers, payload

    @staticmethod
    def _extract(provider_type: str, data: dict[str, Any]) -> str | None:
        if provider_type == "anthropic":
            content = data.get("content") or []
            return "\n".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("text")
            ) or None
        if provider_type == "google":
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            return "\n".join(
                str(item.get("text", ""))
                for item in parts
                if isinstance(item, dict) and item.get("text")
            ) or None
        choices = data.get("choices") or []
        return (
            str(choices[0].get("message", {}).get("content"))
            if choices
            else None
        )


ai_service = AIService()
