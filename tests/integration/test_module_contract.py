from __future__ import annotations

from pathlib import Path

MODULES = {
    "auth",
    "users",
    "organizations",
    "dependencies",
    "checks",
    "incidents",
    "evidence",
    "vendors",
    "notifications",
    "dashboard",
    "billing",
    "api_keys",
}
REQUIRED = {
    "__init__.py",
    "router.py",
    "service.py",
    "repository.py",
    "schemas.py",
    "models.py",
    "constants.py",
}
OPTIONAL = {"tasks.py"}


def test_every_domain_obeys_file_contract() -> None:
    root = Path("app/modules")
    assert {
        item.name for item in root.iterdir() if item.is_dir() and not item.name.startswith("__")
    } == MODULES
    for module in MODULES:
        files = {item.name for item in (root / module).iterdir() if item.is_file()}
        assert REQUIRED <= files
        assert files <= REQUIRED | OPTIONAL
