from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from web_app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_api_menu_status(client):
    response = client.get("/api/menu/status")
    assert response.status_code == 200
    data = response.json()
    assert "has_api_key" in data
    assert "saves" in data
    assert "campaigns" in data
    assert "llm" in data
    assert isinstance(data["saves"], list)
    assert isinstance(data["campaigns"], list)


def test_api_scenarios_list(client):
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert "active_id" in data
    assert isinstance(data["scenarios"], list)


def test_api_state_uninitialized(client):
    response = client.get("/api/state")
    assert response.status_code in (404, 409)


def test_api_scenario_invalid_id(client):
    response = client.get("/api/scenarios/non_existent_scenario_12345")
    assert response.status_code == 404
