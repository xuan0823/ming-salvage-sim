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


def test_game_session_offline_lifecycle(tmp_path):
    from ming_sim.content import GameContent
    from ming_sim.session import GameSession
    from ming_sim.models import LLMConfig

    content = GameContent.load()
    db_file = str(tmp_path / "test_session.db")
    llm_cfg = LLMConfig(api_key="test", base_url="https://api.openai.com/v1", model="test-model")
    session = GameSession(db_file, llm_cfg, content=content, verify_llm=False)
    try:
        snapshot = session.begin_turn()
        assert snapshot.turn == 1
        assert snapshot.year == 1627

        # Add manual directive
        dir_view = session.add_directive("亲裁诏书：清查通州漕粮。")
        assert dir_view.id > 0
        assert session.pending_count() == 0

        # List & update
        directives = session.list_directives()
        assert len(directives) == 1
        session.update_directive(dir_view.id, "亲裁诏书：清查通州与天津漕粮。")

        # Add structured directive
        struct_dir = session.add_structured_directive("emergency_relief", {
            "region": "陕西",
            "method": "开仓放粮",
            "relief_amount": "粮五万石",
            "purpose": "安抚陕北流民",
            "audit": "严查贪墨",
            "note": "专款专办",
        })
        assert struct_dir["template_id"] == "emergency_relief"
        assert len(session.list_structured_directives()) == 1

        # Delete
        session.delete_directive(dir_view.id)
        session.delete_structured_directive(struct_dir["id"])
        assert len(session.list_directives()) == 0
        assert len(session.list_structured_directives()) == 0
    finally:
        session.close()

