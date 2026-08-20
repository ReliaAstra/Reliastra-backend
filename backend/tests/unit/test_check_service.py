import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from sqlalchemy import select

from app.modules.checks.service import CheckService, get_http_client
from app.modules.dependencies.schemas import DependencyInternalDTO


def _fake_dto(dep_id: uuid.UUID, org_id: uuid.UUID) -> DependencyInternalDTO:
    return DependencyInternalDTO(
        id=dep_id,
        org_id=org_id,
        name="Test API",
        endpoint_url="https://example.com/api",
        method="GET",
        headers={},
        expected_status_codes=[200],
        timeout_seconds=5,
        check_interval_seconds=60,
        regions=["us-east", "eu-west"],
        alert_threshold_ms=500,
        is_active=True,
    )


def _fake_dep(dep_id: uuid.UUID, org_id: uuid.UUID) -> MagicMock:
    return MagicMock(id=dep_id, org_id=org_id, is_active=True)


def _wired_repos(dep_id: uuid.UUID, org_id: uuid.UUID, *, is_up: bool = True):
    chk_repo = MagicMock()
    dep_repo = MagicMock()
    fake_result = _fake_result(dep_id, org_id)
    fake_result.is_up = is_up
    dep_repo.get_by_id = AsyncMock(return_value=_fake_dep(dep_id, org_id))
    chk_repo.create = AsyncMock(return_value=fake_result)
    chk_repo.list_recent_for_dependency = AsyncMock(return_value=[fake_result])
    return chk_repo, dep_repo, fake_result


def _fake_result(dep_id: uuid.UUID, org_id: uuid.UUID) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        dependency_id=dep_id,
        org_id=org_id,
        region="us-east",
        executed_at=datetime.now(timezone.utc),
        latency_ms=45.0,
        status_code=200,
        is_up=True,
        error_message=None,
        quorum_confirmed=False,
    )


class _FakePinnedTransport(httpx.AsyncBaseTransport):
    """Fake transport used in place of the real pinned httpcore transport.

    Subclasses ``httpx.AsyncBaseTransport`` so ``httpx.AsyncClient(transport=…)``
    actually routes requests through it (no real network calls in tests).
    """

    def __init__(self, status_code: int = 200, side_effect: Exception | None = None):
        self.status_code = status_code
        self.side_effect = side_effect

    async def handle_async_request(self, request):
        if self.side_effect:
            raise self.side_effect
        return httpx.Response(status_code=self.status_code, request=request)


@pytest.mark.asyncio
async def test_execute_check_success(mocker):
    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        return_value=MagicMock(
            url="https://example.com/api",
            hostname="example.com",
            port=443,
            ips=["93.184.216.34"],
        ),
    ), patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=_FakePinnedTransport(status_code=200),
    ), patch(
        "app.modules.incidents.repository.IncidentRepository.get_open_for_dependency",
        new=AsyncMock(return_value=None),
    ):
        res = await service.execute_check(session, dep_id, "us-east")

    assert res is not None
    assert res.is_up is True
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_execute_check_locks_dependency_row_for_update(mocker):
    """FIX 3: quorum evaluation must run under SELECT ... FOR UPDATE."""
    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()
    executed_statements = []

    async def fake_execute(statement, *args, **kwargs):
        executed_statements.append(statement)
        return MagicMock()

    session.execute = fake_execute

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        return_value=MagicMock(
            url="https://example.com/api",
            hostname="example.com",
            port=443,
            ips=["93.184.216.34"],
        ),
    ), patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=_FakePinnedTransport(status_code=200),
    ), patch(
        "app.modules.incidents.repository.IncidentRepository.get_open_for_dependency",
        new=AsyncMock(return_value=None),
    ):
        await service.execute_check(session, dep_id, "us-east")

    # One of the executed statements must be the FOR UPDATE lock on the
    # dependency row.
    locked = any(
        str(stmt).startswith("SELECT dependencies") and "FOR UPDATE" in str(stmt)
        for stmt in executed_statements
    )
    assert locked, executed_statements


@pytest.mark.asyncio
async def test_execute_check_blocked_url_records_failure_without_http():
    """FIX 26: unsafe URLs never reach an HTTP client."""
    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id, is_up=False)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        side_effect=ValueError("URL safety check failed: private network"),
    ), patch(
        "app.modules.checks.service.pinned_transport_for"
    ) as transport_mock:
        res = await service.execute_check(session, dep_id, "us-east")

    assert res is not None
    assert res.is_up is False
    transport_mock.assert_not_called()
    # The blocked result must be persisted with the security-policy reason.
    _, kwargs = chk_repo.create.call_args
    assert kwargs["is_up"] is False
    assert "blocked" in kwargs["error_message"]
    assert kwargs["status_code"] is None


@pytest.mark.asyncio
async def test_http_client_is_module_level_pool(mocker):
    """FIX 2: get_http_client must return the same pooled client."""
    first = get_http_client()
    second = get_http_client()
    assert first is second
    from app.modules.checks.service import _http_client

    assert _http_client is not None


@pytest.mark.asyncio
async def test_execute_check_records_circuit_breaker(mocker):
    """FIX 8: outcomes feed the circuit breaker."""
    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        return_value=MagicMock(
            url="https://example.com/api",
            hostname="example.com",
            port=443,
            ips=["93.184.216.34"],
        ),
    ), patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=_FakePinnedTransport(status_code=200),
    ), patch(
        "app.modules.incidents.repository.IncidentRepository.get_open_for_dependency",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.modules.checks.service.circuit_breaker.record_success",
        new=AsyncMock(),
    ) as record_success, patch(
        "app.modules.checks.service.circuit_breaker.record_failure",
        new=AsyncMock(),
    ) as record_failure:
        await service.execute_check(session, dep_id, "us-east")

    record_success.assert_awaited_once_with(dep_id)
    record_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_check_writes_observation_outbox(db_session):
    """FIX 9: a check result persists an OutboxEvent in the same transaction."""
    from app.modules.checks.models import CheckResult
    from app.modules.observations.models import OutboxEvent

    service = CheckService()
    result = MagicMock(
        id=uuid.uuid4(),
        dependency_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        region="us-east",
        executed_at=datetime.now(timezone.utc),
        latency_ms=10.0,
        status_code=200,
        is_up=True,
        error_message=None,
        quorum_confirmed=False,
    )
    await service._enqueue_observation_outbox(
        db_session, result, "https://example.com/health", "GET"
    )
    events = (await db_session.execute(select(OutboxEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "observation_created"


@pytest.mark.asyncio
async def test_schedule_due_checks_never_runs_http(db_session, monkeypatch):
    """FIX 4: schedule_due_checks only reads due deps and enqueues."""
    dep_repo = MagicMock()
    dep = MagicMock()
    dep.id = uuid.uuid4()
    dep.regions = ["us-east", "eu-west"]
    dep.next_check_at = datetime.now(timezone.utc)
    dep.check_interval_seconds = 60
    dep_repo.get_due_dependencies = AsyncMock(return_value=[dep])

    service = CheckService(repository=MagicMock(), dep_repository=dep_repo)
    service.execute_check = AsyncMock()

    delayed: list[tuple[str, str]] = []

    class _FakeTask:
        @staticmethod
        def delay(dep_id, region, request_id=None):
            delayed.append((dep_id, region))

    with patch("app.modules.checks.tasks.execute_check", _FakeTask):
        count = await service.schedule_due_checks(AsyncMock())
    assert count == 2
    assert delayed == [(str(dep.id), "us-east"), (str(dep.id), "eu-west")]
    service.execute_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_check_follows_redirects_with_revalidation(mocker):
    """PR #10 + FIX 26: 3xx redirects are followed (bounded), and every hop
    is re-validated against the SSRF policy before connecting."""
    from app.core.ssrf_protection import PinnedTarget

    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    targets = iter([
        PinnedTarget("https://example.com/api", "example.com", 443, ["93.184.216.34"]),
        PinnedTarget("https://www.example.com/api", "www.example.com", 443, ["93.184.216.35"]),
    ])

    def fake_resolve(url):
        return next(targets)

    responses = iter([
        httpx.Response(status_code=302, headers={"location": "https://www.example.com/api"}),
        httpx.Response(status_code=200),
    ])

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return next(responses)

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        side_effect=fake_resolve,
    ), patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=FakeTransport(),
    ), patch(
        "app.modules.incidents.repository.IncidentRepository.get_open_for_dependency",
        new=AsyncMock(return_value=None),
    ):
        res = await service.execute_check(session, dep_id, "us-east")

    assert res.is_up is True
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_execute_check_blocks_redirect_to_private_target():
    """A redirect hop to a blocked target fails the check without a request."""
    from app.core.ssrf_protection import PinnedTarget

    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    fake_dto = _fake_dto(dep_id, org_id)
    chk_repo, dep_repo, fake_result = _wired_repos(dep_id, org_id, is_up=False)

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    first_target = PinnedTarget(
        "https://example.com/api", "example.com", 443, ["93.184.216.34"]
    )
    resolve_calls = {"n": 0}

    def fake_resolve(url):
        if resolve_calls["n"] == 0:
            resolve_calls["n"] += 1
            return first_target
        raise ValueError("URL safety check failed: private network")

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(
                status_code=302, headers={"location": "http://169.254.169.254/steal"}
            )

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch(
        "app.modules.checks.service.resolve_pinned_target",
        side_effect=fake_resolve,
    ), patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=FakeTransport(),
    ):
        res = await service.execute_check(session, dep_id, "us-east")

    assert res.is_up is False
    _, kwargs = chk_repo.create.call_args
    assert "blocked" in kwargs["error_message"]
