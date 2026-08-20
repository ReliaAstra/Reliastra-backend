"""Tests for the asyncpg SSL connect-arg translation (deployment regression).

Regression coverage for the ZevCloud incident where a non-empty
``DATABASE_SSL_MODE`` forced an ``ssl.SSLContext`` on asyncpg, making SSL a
hard requirement.  The in-container PostgreSQL (initdb default ``ssl=off``)
answers the SSLRequest with ``N``, so migrations died with
``ConnectionError: PostgreSQL server at ... rejected SSL upgrade`` and the
deployment rolled back.

The fix maps libpq sslmodes correctly:
* ``disable``  -> ``ssl=False``
* ``allow``/``prefer`` -> no ``ssl`` arg (asyncpg advisory default: try SSL,
  fall back to plaintext)
* ``require``/``verify-ca``/``verify-full`` -> strict SSLContext
"""

import os
import shutil
import socket
import ssl
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db.connect_args import build_ssl_connect_args
from app.db.session import build_engine


@pytest.fixture(autouse=True)
def _isolate_ssl_mode():
    """Run every test with a clean DATABASE_SSL_MODE and restore it after."""
    original = settings.DATABASE_SSL_MODE
    settings.DATABASE_SSL_MODE = ""
    yield
    settings.DATABASE_SSL_MODE = original


# ── Pure mapping tests ───────────────────────────────────────────────────────


def test_empty_mode_returns_no_ssl_arg():
    assert build_ssl_connect_args("") == {}
    assert build_ssl_connect_args(None) == {}


def test_disable_mode_never_negotiates_ssl():
    args = build_ssl_connect_args("disable")
    assert args == {"ssl": False}


@pytest.mark.parametrize("mode", ["allow", "prefer"])
def test_advisory_modes_pass_no_ssl_arg(mode):
    # Passing no `ssl` arg keeps asyncpg's default: SSLRequest is advisory and
    # a plaintext server's `N` answer falls back to a plain connection.
    args = build_ssl_connect_args(mode)
    assert args == {}
    assert "ssl" not in args


def test_require_mode_uses_context_without_verification():
    args = build_ssl_connect_args("require")
    ctx = args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_verify_ca_mode_verifies_cert_but_not_hostname():
    ctx = build_ssl_connect_args("verify-ca")["ssl"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is False


def test_verify_full_mode_verifies_cert_and_hostname():
    ctx = build_ssl_connect_args("verify-full")["ssl"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_ssl_mode_is_case_and_whitespace_insensitive():
    assert build_ssl_connect_args("  REQUIRE ")["ssl"].verify_mode == ssl.CERT_NONE
    assert build_ssl_connect_args("Disable") == {"ssl": False}


def test_unknown_mode_falls_back_to_advisory_ssl():
    # A typo must not hard-require SSL and brick boot against a plaintext DB.
    assert build_ssl_connect_args("requre") == {}


def test_pooler_compat_disables_statement_cache():
    assert build_ssl_connect_args("", pooler_compat=True) == {"statement_cache_size": 0}
    assert build_ssl_connect_args("require", pooler_compat=True)["ssl"] is not None
    assert (
        build_ssl_connect_args("require", pooler_compat=True)["statement_cache_size"]
        == 0
    )


# ── Live engine tests against a PLAINTEXT TCP PostgreSQL ─────────────────────
# pgserver (the main conftest database) listens on a unix socket only, where
# asyncpg skips SSL negotiation entirely — so SSL semantics need TCP.


def _find_pg_bin() -> Path | None:
    initdb = shutil.which("initdb")
    if initdb:
        return Path(initdb).parent
    for candidate in sorted(Path("/usr/lib/postgresql").glob("*/bin")):
        if (candidate / "initdb").exists():
            return candidate
    return None


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _subprocess_env() -> dict:
    env = dict(os.environ)
    # Sandbox nicety: relocated embedded-PG binaries need their bundled libs.
    if Path("/usr/local/lib").exists():
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            filter(None, ["/usr/local/lib", env.get("LD_LIBRARY_PATH", "")])
        )
    return env


@pytest.fixture(scope="module")
def plaintext_tcp_pg(tmp_path_factory):
    """Plaintext PostgreSQL over TCP — exercises real SSLRequest negotiation.

    Starts a throwaway cluster when server binaries are available, otherwise
    falls back to the CI postgres service (also plaintext); skips when
    neither exists.
    """
    pg_bin = _find_pg_bin()
    if pg_bin is None:
        url = "postgresql+asyncpg://reliastra_test:testpass123@localhost:5432/reliastra_test"
        try:
            with socket.create_connection(("127.0.0.1", 5432), timeout=2):
                yield url
                return
        except OSError:
            pytest.skip("no PostgreSQL server binaries and no CI DB service")

    env = _subprocess_env()
    datadir = tmp_path_factory.mktemp("pg_tcp") / "data"
    subprocess.run(
        [
            str(pg_bin / "initdb"),
            "-D",
            str(datadir),
            "--auth=trust",
            "--username=postgres",
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    port = _free_tcp_port()
    subprocess.run(
        [
            str(pg_bin / "pg_ctl"),
            "-D",
            str(datadir),
            "-l",
            str(datadir / "server.log"),
            "-o",
            f"-c listen_addresses='127.0.0.1' -p {port} -c ssl=off",
            "start",
            "-w",
            "-t",
            "60",
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    try:
        yield f"postgresql+asyncpg://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            [str(pg_bin / "pg_ctl"), "-D", str(datadir), "stop", "-m", "immediate"],
            capture_output=True,
            env=env,
            check=False,
        )


def _engine(url: str, ssl_mode: str | None):
    return create_async_engine(
        url, connect_args=build_ssl_connect_args(ssl_mode), pool_pre_ping=True
    )


@pytest.mark.asyncio
async def test_prefer_mode_connects_to_plaintext_postgres(plaintext_tcp_pg):
    """THE regression: 'prefer' must not hard-require SSL (old bug crashed)."""
    engine = _engine(plaintext_tcp_pg, "prefer")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_disable_mode_connects_to_plaintext_postgres(plaintext_tcp_pg):
    engine = _engine(plaintext_tcp_pg, "disable")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_require_mode_fails_against_plaintext_postgres(plaintext_tcp_pg):
    """Documents why the standalone entrypoint must manage local TLS.

    Against a plaintext server (initdb default), a strict mode fails with
    "rejected SSL upgrade" — exactly the deployment incident.  The entrypoint
    enables SSL on the bootstrapped cluster and pins the in-container
    processes to 'prefer' so this can never recur.
    """
    engine = _engine(plaintext_tcp_pg, "require")
    try:
        with pytest.raises(ConnectionError, match="rejected SSL upgrade"):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_build_engine_with_prefer_uses_default_engine_path():
    """Smoke: the production engine builder works with 'prefer' set.

    (Runs against the conftest pgserver instance — a unix socket where
    asyncpg skips SSL — so this guards the build_engine() wiring itself.)
    """
    settings.DATABASE_SSL_MODE = "prefer"
    engine = build_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
