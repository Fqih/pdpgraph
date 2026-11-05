"""Workspace smoke test: every package from 03-architecture §8 imports and ships py.typed (M0.1)."""

import importlib
from importlib import resources

import pytest

PACKAGES = [
    "common",
    "models_aux",
    "pdp_api",
    "pdp_core",
    "pdp_ingest",
    "pdp_mcp",
    "tierline",
    "tierline_router_train",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_m0_1_package_imports_and_is_typed(name: str) -> None:
    module = importlib.import_module(name)
    assert resources.files(module).joinpath("py.typed").is_file()
