"""Pytest configuration and shared fixtures for schrot47_bot tests."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Гарантируем видимость пакета core при запуске pytest из любого каталога
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.evolution_client import EvolutionClient
from core.safety import SafetyManager
from core.sessions import SessionManager


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def session_mgr(temp_db):
    return SessionManager(db_path=temp_db)


@pytest.fixture
def safety_mgr():
    return SafetyManager(
        production_enabled=False,
        outbound_enabled=False,
        owner_only=True,
        kill_switch=True,
    )


@pytest.fixture
def evo_client(safety_mgr):
    return EvolutionClient(
        base_url="http://localhost:8080",
        api_key="test-api-key",
        instance="shrot47_test",
        safety=safety_mgr,
    )
