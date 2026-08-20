"""Shared asyncpg SSL connect-arg construction for the engine and Alembic.

Background (ZevCloud deployment incident, 2026-08-20): the standalone Docker
container overrides ``DATABASE_URL`` to the PostgreSQL it bootstraps inside
the container.  That cluster is created with ``initdb``, whose default is
``ssl = off``.  The platform/README instructs ``DATABASE_SSL_MODE=require``,
and the previous mapping passed an ``ssl.SSLContext`` to asyncpg for *every*
non-empty mode — including ``disable`` and ``prefer``.

asyncpg does not read ``sslmode`` from the URL.  When a Python
``ssl.SSLContext`` is passed via ``connect_args["ssl"]``, SSL becomes a hard
requirement: if the server answers the SSLRequest with ``N`` (no SSL
support), the connection fails with
``ConnectionError: PostgreSQL server at ... rejected SSL upgrade``.

That killed Alembic migrations (and therefore the API) at boot, failing the
container healthcheck and rolling the deployment back.  This module restores
libpq semantics:

* ``disable``     -> ``ssl=False`` (never negotiate SSL)
* ``allow``/``prefer`` -> no ``ssl`` arg (asyncpg default: try SSL, fall back
  to plaintext when the server answers ``N``)
* ``require``     -> SSLContext with CERT_NONE
* ``verify-ca``   -> SSLContext with CERT_REQUIRED, no hostname check
* ``verify-full`` -> SSLContext with CERT_REQUIRED, hostname check enabled
"""

import logging
import ssl as _ssl
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_SSL_MODES = (
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
)


def build_ssl_connect_args(
    ssl_mode: str | None, *, pooler_compat: bool = False
) -> dict[str, Any]:
    """Translate a libpq-style sslmode into asyncpg ``connect_args``.

    Returns a dict suitable for ``create_async_engine(..., connect_args=...)``.
    When *pooler_compat* is True, ``statement_cache_size=0`` is added so
    asyncpg avoids named prepared statements (PgBouncer in transaction mode
    does not support them).
    """
    args: dict[str, Any] = {}

    if ssl_mode:
        mode = ssl_mode.strip().lower()

        if mode == "disable":
            # asyncpg maps ssl=False to sslmode=disable: no SSL negotiation.
            args["ssl"] = False
        elif mode in ("allow", "prefer"):
            # asyncpg's default (ssl=None) is advisory SSL: it attempts the
            # SSL upgrade and falls back to plaintext when the server
            # responds 'N'.  Passing an SSLContext here would instead make
            # SSL a hard requirement and crash against plaintext servers.
            pass
        elif mode in ("require", "verify-ca", "verify-full"):
            ctx = _ssl.create_default_context()
            if mode == "require":
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
            elif mode == "verify-ca":
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_REQUIRED
            else:  # verify-full
                ctx.check_hostname = True
                ctx.verify_mode = _ssl.CERT_REQUIRED
            args["ssl"] = ctx
        else:
            # Unknown value: never let a typo hard-require SSL against a
            # server that may not support it.  Fail safe (boot-safe) with
            # asyncpg's advisory default and say so loudly.
            logger.warning(
                "Unknown DATABASE_SSL_MODE %r — treating as 'prefer' "
                "(SSL when available, plaintext fallback). Supported modes: %s.",
                ssl_mode,
                ", ".join(SUPPORTED_SSL_MODES),
            )

    if pooler_compat:
        args["statement_cache_size"] = 0

    return args
