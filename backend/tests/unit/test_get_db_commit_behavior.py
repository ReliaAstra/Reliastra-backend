"""Tests for FIX 38: get_db commits only dirty sessions."""

from unittest.mock import AsyncMock, MagicMock

import pytest


async def _run_generator(gen) -> None:
    """Drive an async generator past its yield so the after-yield code runs
    (mirrors what FastAPI's dependency machinery does)."""
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        return


@pytest.mark.asyncio
async def test_get_db_rolls_back_clean_sessions(monkeypatch):
    from app.db import session as session_module

    clean_session = AsyncMock()
    clean_session.is_active = True
    clean_session.info = {}
    clean_session.new = set()
    clean_session.deleted = set()
    clean_session.dirty = set()

    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=clean_session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(session_module, "get_session_maker", lambda: maker)

    gen = session_module.get_db()
    session = await gen.__anext__()
    assert session is clean_session
    await _run_generator(gen)

    # No writes → no COMMIT; the transaction is released with a ROLLBACK.
    clean_session.commit.assert_not_awaited()
    clean_session.rollback.assert_awaited()
    clean_session.close.assert_awaited()


@pytest.mark.asyncio
async def test_get_db_commits_dirty_sessions(monkeypatch):
    from app.db import session as session_module

    dirty_session = AsyncMock()
    dirty_session.is_active = True
    dirty_session.info = {}
    dirty_session.new = {object()}
    dirty_session.deleted = set()
    dirty_session.dirty = set()

    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=dirty_session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(session_module, "get_session_maker", lambda: maker)

    gen = session_module.get_db()
    await gen.__anext__()
    await _run_generator(gen)

    dirty_session.commit.assert_awaited()
    dirty_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception(monkeypatch):
    from app.db import session as session_module

    failing = AsyncMock()
    failing.is_active = True
    failing.info = {}
    failing.new = set()
    failing.deleted = set()
    failing.dirty = set()

    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=failing)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(session_module, "get_session_maker", lambda: maker)

    gen = session_module.get_db()
    await gen.__anext__()
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))
    failing.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_get_db_commits_when_writes_were_flushed(monkeypatch):
    """FIX 38: flushed INSERTs (which leave session.new) must still commit."""
    from app.db import session as session_module

    flushed = AsyncMock()
    flushed.is_active = True
    flushed.info = {session_module._WRITE_FLAG: True}
    flushed.new = set()
    flushed.deleted = set()
    flushed.dirty = set()

    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=flushed)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(session_module, "get_session_maker", lambda: maker)

    gen = session_module.get_db()
    await gen.__anext__()
    await _run_generator(gen)

    flushed.commit.assert_awaited()
    flushed.rollback.assert_not_awaited()
