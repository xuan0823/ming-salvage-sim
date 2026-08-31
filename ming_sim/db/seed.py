"""seed_static_data：从 GameContent 灌静态盘面；开局账本/邸报/危机 seed；欠饷单位迁移。

_SeedMixin：拆自原 db.py，方法体逐字未改。"""

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


class _SeedMixin:
    def seed_static_data(self) -> None:
        if not self.table_has_rows("offices"):
            for office_type, definition in self.content.office_definitions.items():
                self.conn.execute(
                    """
                    INSERT INTO offices
                    (office_type, skills, tools, authority_scope, power, responsibility, corruption_risk, court_grant_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        office_type,
                        json.dumps(definition["skills"], ensure_ascii=False),
                        json.dumps(definition["tools"], ensure_ascii=False),
                        str(definition["authority_scope"]),
                        int(definition["power"]),
                        int(definition["responsibility"]),
                        int(definition["corruption_risk"]),
                        json.dumps(self.content.office_court_grants.get(office_type, {}), ensure_ascii=False),
                    ),
                )
        self.init_office_grants()

        # 人物：逐人查重补缺（不再全表 table_has_rows 守卫）。
        # 老档已有的人物一律不动（玩家运行时改过的数据神圣不动）；只插 DB 里没有的。
        # 这样激活自定义剧本后「继续」老档，剧本新增人物会补进来，原有人物不被覆盖。
        # 新档（characters 表为空）退化为全量插入，行为与原来一致。
        new_character_names: List[str] = []
        for character in self.content.characters.values():
            exists = self.conn.execute(
                "SELECT 1 FROM characters WHERE name = ?", (character.name,)
            ).fetchone()
            if exists:
                continue
            office = normalize_office(character.office)
            office_type = infer_office_type_from_office(office, character.office_type)
            self.conn.execute(
                """
                INSERT INTO characters
                (name, office, office_type, faction, aliases, personal_skills, loyalty, ability, integrity, courage, style,
                 diplomacy, martial, stewardship, intrigue, learning,
                 birth_year, historical_death_year, historical_death_month, debut_year, debut_month,
                 status, status_reason, status_changed_turn, portrait_id, power_id, location, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    character.name,
                    office,
                    office_type,
                    character.faction,
                    json.dumps(character.aliases, ensure_ascii=False),
                    json.dumps(character.personal_skills, ensure_ascii=False),
                    character.loyalty,
                    character.ability,
                    character.integrity,
                    character.courage,
                    character.style,
                    character.diplomacy,
                    character.martial,
                    character.stewardship,
                    character.intrigue,
                    character.learning,
                    character.birth_year,
                    character.historical_death_year,
                    character.historical_death_month,
                    character.debut_year,
                    character.debut_month,
                    character.status,
                    "",
                    0,
                    character.portrait_id,
                    character.power_id,
                    character.location,
                    character.summary,
                ),
            )
            new_character_names.append(character.name)
        # character_offices：对新插入的人物补对应行；已有人物的任职履历不动。
        # 兼容老档曾出现「characters 有行但 character_offices 空」的情形：表整体为空时全量补一次。
        if not self.table_has_rows("character_offices"):
            for row in self.conn.execute("SELECT name, office, office_type FROM characters").fetchall():
                self.conn.execute(
                    """
                    INSERT INTO character_offices (character_name, office_title, office_type, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row["name"], row["office"], row["office_type"], "存档迁移"),
                )
        elif new_character_names:
            for row in self.conn.execute(
                "SELECT name, office, office_type FROM characters WHERE name IN ({})".format(
                    ",".join("?" * len(new_character_names))
                ),
                new_character_names,
            ).fetchall():
                self.conn.execute(
                    """
                    INSERT INTO character_offices (character_name, office_title, office_type, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row["name"], row["office"], row["office_type"], "剧本补入"),
                )

        # character_offices 引用的 office_type 可能不在 offices 表（content 的
        # office_definitions 未覆盖「待铨/地方/未仕」等类型）：补默认行，保证声称的 FK 无违规。
        for (office_type,) in self.conn.execute(
            "SELECT DISTINCT office_type FROM characters "
            "UNION SELECT DISTINCT office_type FROM character_offices"
        ).fetchall():
            if self.conn.execute(
                "SELECT 1 FROM offices WHERE office_type = ?", (office_type,)
            ).fetchone() is None:
                self.conn.execute(
                    "INSERT INTO offices (office_type, skills, tools, authority_scope, power, responsibility, corruption_risk, court_grant_json) "
                    "VALUES (?, '[]', '[]', '', 50, 50, 30, '{}')",
                    (office_type,),
                )
        self.conn.commit()

        if not self.table_has_rows("factions"):
            for faction in self.content.factions.values():
                self.conn.execute(
                    """
                    INSERT INTO factions (name, satisfaction, leverage, agenda)
                    VALUES (?, ?, ?, ?)
                    """,
                    (faction.name, faction.satisfaction, faction.leverage, faction.agenda),
                )
        if not self.table_has_rows("classes"):
            for cls in self.content.classes.values():
                self.conn.execute(
                    """
                    INSERT INTO classes (name, region_id, population, satisfaction, leverage, agenda)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (cls.name, cls.region_id, cls.population, cls.satisfaction, cls.leverage, cls.agenda),
                )
        for power in self.content.powers.values():
            self.conn.execute(
                """
                INSERT OR IGNORE INTO powers
                (id, name, kind, leader, stance, leverage, satisfaction, military_strength,
                 cohesion, supply, agenda, status, last_action, aliases)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    power.id,
                    power.name,
                    power.kind,
                    power.leader,
                    power.stance,
                    power.leverage,
                    power.satisfaction,
                    power.military_strength,
                    power.cohesion,
                    power.supply,
                    power.agenda,
                    power.status,
                    power.last_action,
                    power.aliases,
                ),
            )
        for region in self.content.regions.values():
            self.conn.execute(
                """
                INSERT OR IGNORE INTO regions
                (id, name, kind, population, public_support, unrest, natural_disaster, human_disaster,
                 registered_land, hidden_land, tax_per_turn, gentry_resistance,
                 military_pressure, status, controlled_by, fiscal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    region.id,
                    region.name,
                    region.kind,
                    region.population,
                    region.public_support,
                    region.unrest,
                    region.natural_disaster,
                    region.human_disaster,
                    region.registered_land,
                    region.hidden_land,
                    region.tax_per_turn,
                    region.gentry_resistance,
                    region.military_pressure,
                    region.status,
                    region.controlled_by,
                    json.dumps(region.fiscal, ensure_ascii=False),
                ),
            )
        is_fresh_armies_seed = not self.table_has_rows("armies")
        if is_fresh_armies_seed:
            for army in self.content.armies.values():
                self.conn.execute(
                    """
                    INSERT INTO armies
                    (id, name, station, theater, commander, controller, troop_type, troop_composition, manpower,
                     maintenance_per_turn, supply, morale, training, equipment, arrears,
                     mobility, loyalty, status, owner_power)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        army.id,
                        army.name,
                        army.station,
                        army.theater,
                        army.commander,
                        army.controller,
                        army.troop_type,
                        json.dumps(army.troop_composition, ensure_ascii=False),
                        army.manpower,
                        army.maintenance_per_turn,
                        army.supply,
                        army.morale,
                        army.training,
                        army.equipment,
                        army.arrears,
                        army.mobility,
                        army.loyalty,
                        army.status,
                        army.owner_power,
                    ),
                )
            # 开局持械（army_arms）延后到 init_weapons 之后 seed，见 _seed_opening_army_arms。
        if not self.table_has_rows("buildings"):
            for building in self.content.buildings.values():
                self.conn.execute(
                    """
                    INSERT INTO buildings
                    (id, region_id, name, category, level, condition, maintenance, risk,
                     output_metric, output_amount, status, origin, created_turn)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'preset', 0)
                    """,
                    (
                        building.id,
                        building.region_id,
                        building.name,
                        building.category,
                        building.level,
                        building.condition,
                        building.maintenance,
                        building.risk,
                        building.output_metric,
                        building.output_amount,
                        building.status,
                    ),
                )
        if not self.table_has_rows("technologies"):
            for tech in self.content.preset_technologies.values():
                if not getattr(tech, "default_unlocked", False):
                    continue
                self.conn.execute(
                    """
                    INSERT INTO technologies
                    (id, name, category, effect_summary, status, origin, created_turn)
                    VALUES (?, ?, ?, ?, ?, 'preset', 0)
                    """,
                    (
                        f"preset_{tech.key}",
                        tech.name,
                        tech.category,
                        tech.effect_summary,
                        "开局已研成。",
                    ),
                )
        if not self.table_has_rows("events"):
            for event in (*self.content.events, *self.content.seed_events):
                self.conn.execute(
                    """
                    INSERT INTO events
                    (id, title, kind, summary, urgency, severity, credibility, interests, audiences)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.title,
                        event.kind,
                        event.summary,
                        event.urgency,
                        event.severity,
                        event.credibility,
                        json.dumps(event.interests, ensure_ascii=False),
                        json.dumps(event.audiences, ensure_ascii=False),
                    ),
                )
        self._migrate_arrears_unit_to_silver(is_fresh_armies_seed)
        self.init_weapons()
        self.init_troop_tiers()
        if is_fresh_armies_seed:
            self._seed_opening_army_arms()
        self.conn.commit()

    def _seed_opening_army_arms(self) -> None:
        """开局把 armies.json 各军的 arms（军→兵种→装备）写进 army_arms。
        须在 init_weapons 之后（要 weapons 表解析型号 name→id）。只新档 seed 一次。"""
        for army in self.content.armies.values():
            for entry in getattr(army, "arms", []) or []:
                troop = str(entry.get("troop_type") or "")
                wname = str(entry.get("weapon") or "")
                qty = int(entry.get("qty") or 0)
                if not wname or qty <= 0:
                    continue
                w = self._ensure_weapon_registered(wname)
                if w is None:
                    print(f"[WARN] 开局持械型号无法解析：{wname}（{army.name}）→ 跳过")
                    continue
                self.conn.execute(
                    """
                    INSERT INTO army_arms (army_id, troop_type, weapon_id, qty) VALUES (?, ?, ?, ?)
                    ON CONFLICT(army_id, troop_type, weapon_id)
                      DO UPDATE SET qty=excluded.qty, updated_at=CURRENT_TIMESTAMP
                    """,
                    (army.id, troop, str(w["id"]), qty),
                )

    def _migrate_arrears_unit_to_silver(self, is_fresh_armies_seed: bool) -> None:
        """一次性迁移：armies.arrears 从 0-100 抽象分换成累计欠饷万两。
        旧档按 arrears * maintenance_per_turn / 25 估算（粗略：旧分数 ≈ 4 倍欠饷月数）。

        区分新老档：
        - 新档（is_fresh_armies_seed=True）：armies 由本版 seed_armies 刚刚写入，arrears
          已经是万两。直接打 version=1，跳过换算。
        - 老档（is_fresh_armies_seed=False）：armies 表早已存在数据；若 fiscal_config 中
          无 __arrears_unit_version 标记，说明从未跑过本迁移 → 走换算逻辑。
        """
        ARREARS_UNIT_VERSION = 1
        row = self.conn.execute(
            "SELECT value FROM fiscal_config WHERE key = '__arrears_unit_version'"
        ).fetchone()
        cur = int(row["value"]) if row else 0
        if cur >= ARREARS_UNIT_VERSION:
            return
        if not is_fresh_armies_seed:
            # 真老档：换算分数 → 万两
            self.conn.execute(
                "UPDATE armies SET arrears = CAST(arrears * maintenance_per_turn / 25.0 AS INTEGER) "
                "WHERE maintenance_per_turn > 0"
            )
        # 无论新老档，都把 version 打上，下次启动直接跳过
        self.conn.execute(
            "INSERT INTO fiscal_config (key, value, kind, note) VALUES "
            "('__arrears_unit_version', ?, 'meta', 'arrears 单位由 0-100 分迁至累计欠饷万两的版本号') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, note = excluded.note",
            (ARREARS_UNIT_VERSION,),
        )

    def sync_economy_accounts(self, state: GameState) -> None:
        notes = {
            "国库": "朝廷公开财政，用于军饷、赈济、官俸和工程。",
            "内库": "皇帝可直接调度的钱物，用于救急、密支和政治缓冲。",
        }
        for account in ECONOMY_ACCOUNTS:
            self.conn.execute(
                """
                INSERT INTO economy_accounts (account, metric_key, balance, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account) DO UPDATE SET
                    balance = excluded.balance,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (account, account, float(state.metrics[account]), notes[account]),
            )

    def ensure_opening_ledger(self, state: GameState) -> None:
        for account in ECONOMY_ACCOUNTS:
            exists = self.conn.execute(
                "SELECT 1 FROM economy_ledger WHERE account = ? LIMIT 1",
                (account,),
            ).fetchone()
            if exists:
                continue
            balance = float(state.metrics[account])
            self.conn.execute(
                """
                INSERT INTO economy_ledger
                (turn, year, period, account, delta, balance_after, category, reason, actor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (state.turn, state.year, state.period, account, balance, balance, "期初", "登基初始账册", "内阁"),
            )
        self.conn.commit()

    def seed_opening_gazette(self, state: GameState) -> None:
        """新档塞一份「即位前一月」邸报（turn=state.turn-1），让大臣首回合即可经 read_past_report
        查到开局朝局速览，不必凭空臆议。已存在则不覆盖。文本来自 content/opening_gazette.md。"""
        prev_turn = state.turn - 1
        prev_year, prev_period = state.year, state.period - 1
        if prev_period < 1:
            prev_period = 12
            prev_year -= 1
        exists = self.conn.execute(
            "SELECT 1 FROM turn_reports WHERE turn = ?",
            (prev_turn,),
        ).fetchone()
        if exists is not None:
            return
        from pathlib import Path
        from ming_sim.paths import bundled_path
        gazette_path = Path(bundled_path("content", "opening_gazette.md"))
        if not gazette_path.is_file():
            return
        text = gazette_path.read_text(encoding="utf-8").strip()
        if not text:
            return
        self.conn.execute(
            "INSERT INTO turn_reports (turn, year, period, report) VALUES (?, ?, ?, ?)",
            (prev_turn, prev_year, prev_period, text),
        )
        self.conn.commit()

    def seed_opening_crises(self, state: GameState) -> None:
        """新档首次进入时塞 1627 即位即面对的危机为 active situation issue。
        数据源已并入 seed_events.json：取标了 auto_trigger 且 trigger_gate 为空（开局盘面无条件
        即达标）的 situation 事件，开局直接立项，使玩家召见前就看到三大危机。
        其余带 gate 的 seed 事件靠 auto_trigger_seed_issues 在 gate 达标的回合再硬立。"""
        if not getattr(self, "content", None):
            return
        for ev in self.content.seed_events:
            if not ev.auto_trigger or ev.trigger_gate:
                continue
            if ev.event_type != "situation":
                continue
            if self.find_any_issue_by_origin("event_pool", ev.id) is not None:
                continue
            # 推导默认 bar / inertia / ongoing / effect，与 event_to_issue 同口径；精调字段优先
            bar = ev.bar_value or max(20, min(60, 50 - int(ev.severity / 5)))
            inertia = ev.issue_inertia  # 默认 0=不漂；要月漂在 seed 里显式填
            try:
                self.insert_issue(
                    state,
                    kind="situation",
                    title=ev.title,
                    origin_kind="event_pool",
                    origin_ref=ev.id,
                    bar_value=bar,
                    bar_good_meaning=ev.bar_good_meaning or "已平",
                    bar_bad_meaning=ev.bar_bad_meaning or "失控",
                    inertia=inertia,
                    stage_text=ev.stage_text or ev.summary[:80],
                    severity=int(ev.severity),
                    region_hint=ev.region_hint,
                    faction_hint=",".join(ev.interests[:2]),
                    tags=ev.issue_tags or [ev.kind],
                    ongoing_effects=ev.ongoing_effects,
                    cancellable="never",
                    effect_on_resolve=ev.effect_on_resolve,
                    effect_on_fail=ev.effect_on_fail,
                    resolve_condition=ev.resolve_condition,
                    fail_condition=ev.fail_condition,
                )
            except Exception as exc:
                print(f"[WARN] 开局危机落库失败：{exc}；跳过 {ev.title}")
