import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.security import decrypt_jsonb, encrypt_jsonb
from app.core.ssrf_protection import (
    pinned_transport_for,
    resolve_pinned_target,
    validate_outbound_url,
)
from app.modules.ai_integration.models import AIProvider
from app.modules.ai_integration.repository import AIProviderRepository
from app.modules.ai_integration.schemas import (
    AIProviderCreateRequest,
    AIProviderResponse,
    AIProviderUpdateRequest,
)

logger = logging.getLogger(__name__)

# Prompt/context limits to bound memory and PDF size.
MAX_CONTEXT_JSON_CHARS = 6000
MAX_EXPLANATION_CHARS = 4000
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 0.5


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
        try:
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
            # Flush will hit the partial unique index; convert race to 409/validation.
            await session.flush()
        except IntegrityError as exc:
            # Concurrent is_default=true race — DB enforces at most one default.
            await session.rollback()
            raise ValidationException(
                "A default AI provider already exists for this organization. "
                "Unset the existing default before creating another."
            ) from exc

        try:
            await AuditLogService.log_event(
                session=session,
                event_type="AI_PROVIDER_CREATED",
                org_id=org_id,
                resource_type="ai_provider",
                resource_id=str(provider.id),
                payload={
                    "provider_type": provider.provider_type,
                    "model_name": provider.model_name,
                    "is_default": provider.is_default,
                },
            )
        except Exception:
            logger.debug("Failed to write audit log for AI provider create", exc_info=True)

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
        try:
            updated = await self.repository.update(session, provider, **values)
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise ValidationException(
                "A default AI provider already exists for this organization."
            ) from exc

        try:
            await AuditLogService.log_event(
                session=session,
                event_type="AI_PROVIDER_UPDATED",
                org_id=org_id,
                resource_type="ai_provider",
                resource_id=str(updated.id),
                payload={"updated_fields": list(values.keys())},
            )
        except Exception:
            logger.debug("Failed to write audit log for AI provider update", exc_info=True)

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
        try:
            await AuditLogService.log_event(
                session=session,
                event_type="AI_PROVIDER_DELETED",
                org_id=org_id,
                resource_type="ai_provider",
                resource_id=str(provider_id),
                payload={"name": provider.name},
            )
        except Exception:
            logger.debug("Failed to write audit log for AI provider delete", exc_info=True)

    # ------------------------------------------------------------------
    # Test connectivity — validates endpoint + credentials without
    # persisting anything. Used by the POST /{id}/test route.
    # ------------------------------------------------------------------
    async def test_provider(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        provider_id: uuid.UUID,
    ) -> dict[str, Any]:
        provider = await self.repository.get_by_id(session, provider_id)
        if not provider or provider.organization_id != org_id:
            raise ResourceNotFoundException("AI provider not found")
        key_data = decrypt_jsonb(provider.encrypted_api_key)
        api_key = key_data.get("api_key") if key_data else None
        if not api_key:
            raise ValidationException("Provider has no API key configured")
        # Minimal prompt for connectivity check
        return await self._call_provider(
            provider, str(api_key), "Connectivity test — respond with 'ok'."
        )

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
            logger.info("No active default AI provider for org %s — skipping AI explanation", org_id)
            return None
        key_data = decrypt_jsonb(provider.encrypted_api_key)
        # decrypt_jsonb returns {} on Fernet failure (rotated SECRET_KEY); treat as missing
        if key_data is not None and not key_data:
            logger.warning(
                "AI provider %s API key decrypt returned empty — likely SECRET_KEY rotation; skipping",
                provider.id,
            )
            return None
        api_key = key_data.get("api_key") if key_data else None
        if not api_key:
            logger.warning("AI provider %s has no API key — skipping", provider.id)
            return None

        # Bound context size — prevent prompt injection / huge payloads
        try:
            context_json = json.dumps(context, sort_keys=True, ensure_ascii=False)
        except Exception:
            context_json = str(context)
        if len(context_json) > MAX_CONTEXT_JSON_CHARS:
            context_json = context_json[:MAX_CONTEXT_JSON_CHARS] + "...[truncated]"

        prompt = (
            "You are a technical evidence explainer. Explain only the supplied "
            "pre-computed evidence. Do not invent measurements, conclusions, or "
            "facts. Do not alter the attribution result or confidence score.\n\n"
            f"Instruction: {instruction}\n\nEvidence Data:\n{context_json}\n\n"
            "Use clear language and state that this is an AI-generated explanation."
        )

        try:
            result = await self._call_provider(provider, str(api_key), prompt)
            text = result.get("text")
            if text:
                # Bound output — protects PDF size / storage
                if len(text) > MAX_EXPLANATION_CHARS:
                    text = text[:MAX_EXPLANATION_CHARS] + "...[truncated]"
                return text
            return None
        except ValidationException:
            # SSRF validation errors — don't retry, surface as warning
            logger.warning("AI provider %s endpoint failed safety check", provider.id)
            return None
        except Exception as exc:
            logger.warning("AI generation failed for provider %s: %s", provider.id, exc)
            return None

    async def _call_provider(
        self, provider: AIProvider, api_key: str, prompt: str
    ) -> dict[str, Any]:
        """Pinned, retrying HTTP call to the provider. Returns {'text': str|None}."""
        # Metrics
        from app.core.metrics import ai_generation_latency, ai_generation_total

        start = time.monotonic()
        # Resolve + pin DNS once — closes DNS-rebinding TOCTOU
        try:
            target = resolve_pinned_target(provider.endpoint_url)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

        transport = pinned_transport_for(target)
        headers, payload = self._request(provider, api_key, prompt)

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    transport=transport, timeout=30
                ) as client:
                    response = await client.post(
                        provider.endpoint_url, headers=headers, json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    text = self._extract(provider.provider_type, data)
                    elapsed = time.monotonic() - start
                    try:
                        ai_generation_total.labels(
                            provider_type=provider.provider_type, status="success"
                        ).inc()
                        ai_generation_latency.labels(
                            provider_type=provider.provider_type
                        ).observe(elapsed)
                    except Exception:
                        pass
                    return {"text": text, "raw": data}
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else 0
                # Retry only on transient errors
                if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                try:
                    ai_generation_total.labels(
                        provider_type=provider.provider_type, status="error"
                    ).inc()
                except Exception:
                    pass
                raise
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                try:
                    ai_generation_total.labels(
                        provider_type=provider.provider_type, status="error"
                    ).inc()
                except Exception:
                    pass
                raise
            except Exception as exc:
                last_exc = exc
                try:
                    ai_generation_total.labels(
                        provider_type=provider.provider_type, status="error"
                    ).inc()
                except Exception:
                    pass
                raise

        if last_exc:
            raise last_exc
        return {"text": None}

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
