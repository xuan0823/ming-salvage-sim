"""game_state / metrics：开局判定、存读档、上回合摘要。

_StateMixin。上回合摘要只读 turn_reports（turn_logs 已废）。"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ming_sim.assets import format_money, format_money_delta
from ming_sim.constants import (
    ARMY_FIELD_ALIASES, ARMY_FIELD_LABELS, ARMY_QUANTITY_FIELDS, ARMY_SCORE_FIELDS, ARMY_TEXT_FIELDS,
    BUILDING_CATEGORIES, BUILDING_FIELD_LABELS, BUILDING_OUTPUT_METRICS,
    BUILDING_QUANTITY_FIELDS, BUILDING_SCORE_FIELDS, BUILDING_TEXT_FIELDS,
    ECONOMY_ACCOUNTS, POWER_FIELD_LABELS, POWER_SCORE_FIELDS,
    POWER_FIELD_ALIASES, POWER_TEXT_FIELDS, MONEY_UNIT, REGION_FIELD_LABELS, REGION_QUANTITY_FIELDS,
    FISCAL_SCORE_FIELDS, REGION_FIELD_ALIASES, REGION_SCORE_FIELDS, REGION_TEXT_FIELDS, TURN_UNIT,
)
from ming_sim.content import GameContent
from ming_sim.matching import match_army_id_from_text, match_region_id_from_text
from ming_sim.models import Event, GameState, monthly_amount, period_label
from ming_sim.token_stats import tlog
from ming_sim.db._helpers import (
    normalize_office, infer_office_type_from_office,
    _compact_lookup_text, _normalize_power_id,
    COURT_OFFICE_TYPES, MINISTRY_OFFICE_TYPES,
)


class _StateMixin:
    def has_state(self) -> bool:
        row = self.conn.execute("SELECT 1 FROM game_state WHERE id = 1").fetchone()
        return row is not None

    def save_state(self, state: GameState) -> None:
        self.conn.execute(
            """
            INSERT INTO game_state (id, year, period, turn, turn_phase, ended, ending_status)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET year = excluded.year, period = excluded.period,
                turn = excluded.turn, turn_phase = excluded.turn_phase,
                ended = excluded.ended, ending_status = excluded.ending_status
            """,
            (
                state.year, state.period, state.turn, state.turn_phase,
                1 if state.ended else 0, state.ending_status,
            ),
        )
        for key, value in state.metrics.items():
            self.conn.execute(
                """
                INSERT INTO metrics (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
        self.sync_economy_accounts(state)
        self.conn.commit()

    def load_state(self, start_ym: str = "") -> GameState:
        row = self.conn.execute(
            "SELECT year, period, turn, turn_phase, ended, ending_status FROM game_state WHERE id = 1"
        ).fetchone()
        if row is None:
            state = GameState()
            if start_ym:
                try:
                    y_str, m_str = start_ym.split(".")
                    y, m = int(y_str), int(m_str)
                except (ValueError, AttributeError):
                    raise SystemExit(f"--start-ym 格式非法：{start_ym!r}，应为 YYYY.MM（如 1629.04）。")
                if not (1627 <= y <= 1644 and 1 <= m <= 12):
                    raise SystemExit(f"--start-ym 超范围：{start_ym!r}，年须 1627-1644、月 1-12。")
                if y == 1627 and m < 10:
                    raise SystemExit(f"--start-ym 早于登基：{start_ym!r}，1627 年须从 10 月起（1627.10=turn 1）。")
                state.turn = (y - 1627) * 12 + (m - 10) + 1
                state.year, state.period = y, m
                print(f"[调试] 跳到 {y}年{m}月起手（turn={state.turn}）。")
            self.save_state(state)
            self.ensure_opening_ledger(state)
            self.seed_opening_crises(state)
            self.seed_opening_gazette(state)
            return state
        metrics = {
            metric["key"]: float(metric["value"])
            for metric in self.conn.execute("SELECT key, value FROM metrics").fetchall()
        }
        state = GameState(
            year=int(row["year"]), period=int(row["period"]), turn=int(row["turn"]),
            turn_phase=str(row["turn_phase"] or "summoning"),
            ended=bool(row["ended"]) if "ended" in row.keys() else False,
            ending_status=str(row["ending_status"] or "") if "ending_status" in row.keys() else "",
        )
        if metrics:
            # 只接当前 GameState 默认 dict 里有的 key，避免旧 DB 残留废弃 metric 灌入。
            valid_keys = set(state.metrics.keys())
            state.metrics.update({k: v for k, v in metrics.items() if k in valid_keys})
        account_rows = self.conn.execute("SELECT account, balance FROM economy_accounts").fetchall()
        for account in account_rows:
            account_name = str(account["account"])
            balance = float(account["balance"])
            state.metrics[account_name] = balance
        self.sync_economy_accounts(state)
        self.ensure_opening_ledger(state)
        self.conn.commit()
        return state

    def previous_turn_summary(self, state: GameState) -> str:
        previous_turn = state.turn - 1
        # turn=0 是开局即位邸报（seed_opening_gazette 落库）；turn<0 才算未登基前。
        if previous_turn < 0:
            return f"登基伊始，尚无上{TURN_UNIT}回奏。"

        # 上回合奏报单独存在 turn_reports，直接取。
        report = self.get_turn_report(previous_turn)
        if report:
            return report
        if previous_turn == 0:
            return f"登基伊始，尚无上{TURN_UNIT}回奏。"
        return f"上{TURN_UNIT}未见正式记录。"
