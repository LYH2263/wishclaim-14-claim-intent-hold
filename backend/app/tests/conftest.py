import os
import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point every test at its own throwaway SQLite directory."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield
