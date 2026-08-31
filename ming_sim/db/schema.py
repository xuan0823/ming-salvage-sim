"""init_schema：全部 41 张表 DDL + 旧库补列迁移。

_SchemaMixin：拆自原 db.py，方法体逐字未改。"""

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


class _SchemaMixin:
    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                turn INTEGER NOT NULL,
                turn_phase TEXT NOT NULL DEFAULT 'summoning'
            );

            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS offices (
                office_type TEXT PRIMARY KEY,
                skills TEXT NOT NULL,
                tools TEXT NOT NULL,
                authority_scope TEXT NOT NULL,
                power INTEGER NOT NULL,
                responsibility INTEGER NOT NULL,
                corruption_risk INTEGER NOT NULL,
                court_grant_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS characters (
                name TEXT PRIMARY KEY,
                office TEXT NOT NULL,
                office_type TEXT NOT NULL,
                faction TEXT NOT NULL,
                personal_skills TEXT NOT NULL,
                loyalty INTEGER NOT NULL,
                ability INTEGER NOT NULL,
                integrity INTEGER NOT NULL,
                courage INTEGER NOT NULL,
                diplomacy INTEGER NOT NULL DEFAULT 50,
                martial INTEGER NOT NULL DEFAULT 50,
                stewardship INTEGER NOT NULL DEFAULT 50,
                intrigue INTEGER NOT NULL DEFAULT 50,
                learning INTEGER NOT NULL DEFAULT 50,
                style TEXT NOT NULL,
                birth_year INTEGER NOT NULL DEFAULT 0,
                historical_death_year INTEGER NOT NULL DEFAULT 0,
                historical_death_month INTEGER NOT NULL DEFAULT 0,
                debut_year INTEGER NOT NULL DEFAULT 0,
                debut_month INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                status_reason TEXT NOT NULL DEFAULT '',
                status_changed_turn INTEGER NOT NULL DEFAULT 0,
                power_id TEXT NOT NULL DEFAULT 'ming',
                location TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT 'preset',
                archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS character_offices (
                character_name TEXT PRIMARY KEY,
                office_title TEXT NOT NULL,
                office_type TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(character_name) REFERENCES characters(name),
                FOREIGN KEY(office_type) REFERENCES offices(office_type)
            );

            CREATE TABLE IF NOT EXISTS factions (
                name TEXT PRIMARY KEY,
                satisfaction INTEGER NOT NULL,
                leverage INTEGER NOT NULL,
                agenda TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS powers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                leader TEXT NOT NULL,
                stance TEXT NOT NULL,
                leverage INTEGER NOT NULL,
                satisfaction INTEGER NOT NULL,
                military_strength INTEGER NOT NULL,
                cohesion INTEGER NOT NULL,
                supply INTEGER NOT NULL,
                agenda TEXT NOT NULL,
                status TEXT NOT NULL,
                last_action TEXT NOT NULL DEFAULT '',
                aliases TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS power_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                power_id TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                delta INTEGER,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(power_id) REFERENCES powers(id)
            );

            CREATE TABLE IF NOT EXISTS power_name_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                power_id TEXT NOT NULL,
                old_name TEXT NOT NULL,
                new_name TEXT NOT NULL,
                old_aliases TEXT NOT NULL DEFAULT '',
                new_aliases TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(power_id) REFERENCES powers(id)
            );

            CREATE TABLE IF NOT EXISTS regions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                population INTEGER NOT NULL,
                public_support INTEGER NOT NULL,
                unrest INTEGER NOT NULL,
                natural_disaster TEXT NOT NULL,
                human_disaster TEXT NOT NULL,
                registered_land INTEGER NOT NULL,
                hidden_land INTEGER NOT NULL,
                tax_per_turn INTEGER NOT NULL,
                gentry_resistance INTEGER NOT NULL,
                military_pressure INTEGER NOT NULL,
                status TEXT NOT NULL,
                controlled_by TEXT NOT NULL DEFAULT 'ming',
                fiscal TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(controlled_by) REFERENCES powers(id)
            );

            CREATE TABLE IF NOT EXISTS region_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                region_id TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                delta INTEGER,
                reason TEXT NOT NULL,
                event_id TEXT,
                edict_id INTEGER,
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(region_id) REFERENCES regions(id)
            );

            CREATE TABLE IF NOT EXISTS armies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                station TEXT NOT NULL,
                theater TEXT NOT NULL,
                commander TEXT NOT NULL,
                controller TEXT NOT NULL,
                troop_type TEXT NOT NULL,
                troop_composition TEXT NOT NULL DEFAULT '{}',
                manpower INTEGER NOT NULL,
                maintenance_per_turn INTEGER NOT NULL,
                supply INTEGER NOT NULL,
                morale INTEGER NOT NULL,
                training INTEGER NOT NULL,
                equipment INTEGER NOT NULL,
                arrears INTEGER NOT NULL,
                mobility INTEGER NOT NULL,
                loyalty INTEGER NOT NULL,
                status TEXT NOT NULL,
                owner_power TEXT NOT NULL DEFAULT 'ming',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_power) REFERENCES powers(id)
            );

            CREATE TABLE IF NOT EXISTS army_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                army_id TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                delta INTEGER,
                reason TEXT NOT NULL,
                event_id TEXT,
                edict_id INTEGER,
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(army_id) REFERENCES armies(id)
            );

            CREATE TABLE IF NOT EXISTS buildings (
                id TEXT PRIMARY KEY,
                region_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                level INTEGER NOT NULL,
                condition INTEGER NOT NULL,
                maintenance INTEGER NOT NULL,
                risk INTEGER NOT NULL,
                output_metric TEXT NOT NULL DEFAULT '',
                output_amount INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'preset',
                requires_tech TEXT NOT NULL DEFAULT '',
                created_turn INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(region_id) REFERENCES regions(id)
            );

            CREATE TABLE IF NOT EXISTS building_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                building_id TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                delta INTEGER,
                reason TEXT NOT NULL,
                event_id TEXT,
                edict_id INTEGER,
                actor TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(building_id) REFERENCES buildings(id)
            );

            CREATE TABLE IF NOT EXISTS technologies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                effect_summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT 'issue',
                created_turn INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- 军事装备型号注册表（weapons.json 打底 + 运行时 LLM 新增）
            CREATE TABLE IF NOT EXISTS weapons (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT '',
                cost INTEGER NOT NULL DEFAULT 1,
                equip_per_unit REAL NOT NULL DEFAULT 0.4,
                requires_tech TEXT NOT NULL DEFAULT '',
                registered TEXT NOT NULL DEFAULT 'seed',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- 兵种档注册表（troop_cost.json 打底 + 运行时 LLM 新增）：requires_tech 门控编制（须研成科技）。
            -- 装备维度（升级须有对应实物装备、按持械量定升级人数）由 AI 软判，不在此表门控。
            CREATE TABLE IF NOT EXISTS troop_tiers (
                name TEXT PRIMARY KEY,
                category TEXT NOT NULL DEFAULT '',
                per_kilo REAL NOT NULL DEFAULT 0,
                requires_tech TEXT NOT NULL DEFAULT '',
                registered TEXT NOT NULL DEFAULT 'seed',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- 国家军备总库：一行一型号
            CREATE TABLE IF NOT EXISTS arms_stock (
                weapon_id TEXT PRIMARY KEY,
                qty INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(weapon_id) REFERENCES weapons(id)
            );

            -- 拨发到军：某军持有某型号几件
            -- 拨发到军：某军「某兵种」持有某型号几件（军→兵种→装备三级）。
            -- troop_type＝兵种名（armies.troop_composition 的 key，归一闭集名）。
            CREATE TABLE IF NOT EXISTS army_arms (
                army_id TEXT NOT NULL,
                troop_type TEXT NOT NULL DEFAULT '',
                weapon_id TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(army_id, troop_type, weapon_id),
                FOREIGN KEY(army_id) REFERENCES armies(id),
                FOREIGN KEY(weapon_id) REFERENCES weapons(id)
            );

            -- 军备变更流水（产出/拨发/战损溯源，army_id 为 NULL=总库变更）
            CREATE TABLE IF NOT EXISTS arms_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                weapon_id TEXT NOT NULL,
                army_id TEXT,
                old_value INTEGER NOT NULL,
                new_value INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS economy_accounts (
                account TEXT PRIMARY KEY,
                metric_key TEXT NOT NULL UNIQUE,
                balance INTEGER NOT NULL,
                note TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS economy_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                account TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                event_id TEXT,
                edict_id INTEGER,
                actor TEXT,
                purpose TEXT,
                target_kind TEXT,
                target_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account) REFERENCES economy_accounts(account)
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                urgency INTEGER NOT NULL,
                severity INTEGER NOT NULL,
                credibility INTEGER NOT NULL,
                interests TEXT NOT NULL,
                audiences TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_triggers (
                event_id TEXT PRIMARY KEY,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'simulation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS turn_reports (
                turn INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                report TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- 推演链每个 agent 的原始输入/输出留痕，每回合一行，便于事后追查。
            CREATE TABLE IF NOT EXISTS turn_extractions (
                turn INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                decree_text TEXT NOT NULL DEFAULT '',
                narrative TEXT NOT NULL DEFAULT '',
                extractor_input TEXT NOT NULL DEFAULT '',
                extractor_output TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- HITL 决策点 + phase1 推演上下文不落库：由 GameSession 持进程内存
            -- （_pending_decisions / _pending_resolve_ctx）。决策暂停期间进程重启即丢，
            -- 按重跑推演处理（不扛续跑）。原 pending_decisions / pending_resolve_context 已废。

            -- 召对聊天记录持久化，每条消息一行，进程重启不丢。
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                minister_name TEXT NOT NULL,
                turn INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_chat_messages_minister
                ON chat_messages(minister_name, id);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_turn
                ON chat_messages(turn);

            -- 朝会聊天室记录：一月一个 session，以 turn 分组；speaker 记录皇帝/大臣名。
            CREATE TABLE IF NOT EXISTS court_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                role TEXT NOT NULL,
                speaker TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_court_chat_messages_turn
                ON court_chat_messages(turn, id);

            -- 原召对撤回表 chat_turns / chat_turn_rollback_items 已废：召对中途退出＝前端中断
            -- 线程，整轮不落库（副作用循环在流式跑完后才执行，中断即无副作用），无需事后回滚。

            CREATE TABLE IF NOT EXISTS secret_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_issued INTEGER NOT NULL,
                due_turn INTEGER NOT NULL DEFAULT 0,
                year_issued INTEGER NOT NULL,
                period_issued INTEGER NOT NULL,
                minister_name TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                importance INTEGER NOT NULL DEFAULT 4,
                status TEXT NOT NULL DEFAULT 'active',
                result TEXT NOT NULL DEFAULT '',
                sim_note TEXT NOT NULL DEFAULT '',
                turn_closed INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_secret_orders_minister
                ON secret_orders(minister_name, status);
            CREATE INDEX IF NOT EXISTS idx_secret_orders_turn
                ON secret_orders(turn_issued, status);
            CREATE INDEX IF NOT EXISTS idx_secret_orders_status
                ON secret_orders(status);

            CREATE TABLE IF NOT EXISTS skill_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                granted_by TEXT NOT NULL,
                source_turn INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(character_name) REFERENCES characters(name)
            );

            CREATE TABLE IF NOT EXISTS turn_directives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                event_id TEXT,
                actor TEXT,
                skill_id TEXT,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(event_id) REFERENCES events(id),
                FOREIGN KEY(actor) REFERENCES characters(name)
            );

            CREATE TABLE IF NOT EXISTS turn_structured_directives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                template_id TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                fields_json TEXT NOT NULL,
                compiled_text TEXT NOT NULL,
                settlement_hint TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_economy_ledger_turn
            ON economy_ledger(turn, account);

            CREATE TABLE IF NOT EXISTS fiscal_config (
                key   TEXT PRIMARY KEY,
                value INTEGER NOT NULL,
                kind  TEXT NOT NULL,
                note  TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_turn_directives_turn
            ON turn_directives(turn, status);

            CREATE INDEX IF NOT EXISTS idx_structured_directives_turn
            ON turn_structured_directives(turn, status);

            CREATE INDEX IF NOT EXISTS idx_region_logs_turn
            ON region_logs(turn, region_id);

            CREATE INDEX IF NOT EXISTS idx_army_logs_turn
            ON army_logs(turn, army_id);

            CREATE INDEX IF NOT EXISTS idx_building_logs_turn
            ON building_logs(turn, building_id);

            CREATE INDEX IF NOT EXISTS idx_power_logs_turn
            ON power_logs(turn, power_id);

            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                origin_kind TEXT NOT NULL DEFAULT '',
                origin_ref TEXT NOT NULL DEFAULT '',
                origin_turn INTEGER NOT NULL,
                bar_value INTEGER NOT NULL DEFAULT 40,
                bar_good_meaning TEXT NOT NULL DEFAULT '已平',
                bar_bad_meaning TEXT NOT NULL DEFAULT '失控',
                inertia INTEGER NOT NULL DEFAULT 0,
                phase TEXT NOT NULL DEFAULT '起',
                stage_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                severity INTEGER NOT NULL DEFAULT 50,
                region_hint TEXT NOT NULL DEFAULT '',
                faction_hint TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                ongoing_effects TEXT NOT NULL DEFAULT '{}',
                cancellable TEXT NOT NULL DEFAULT 'never',
                cancel_cost TEXT NOT NULL DEFAULT '{}',
                effect_on_resolve TEXT NOT NULL DEFAULT '{}',
                effect_on_fail TEXT NOT NULL DEFAULT '{}',
                resolve_condition TEXT NOT NULL DEFAULT '',
                fail_condition TEXT NOT NULL DEFAULT '',
                assignee TEXT NOT NULL DEFAULT '',
                resolution_summary TEXT NOT NULL DEFAULT '',
                last_advance_turn INTEGER NOT NULL DEFAULT 0,
                closed_turn INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS issue_advances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL DEFAULT 0,
                period INTEGER NOT NULL DEFAULT 0,
                trigger_kind TEXT NOT NULL,
                trigger_ref TEXT NOT NULL DEFAULT '',
                delta_bar INTEGER NOT NULL DEFAULT 0,
                from_value INTEGER NOT NULL DEFAULT 0,
                to_value INTEGER NOT NULL DEFAULT 0,
                from_stage_text TEXT NOT NULL DEFAULT '',
                to_stage_text TEXT NOT NULL DEFAULT '',
                narrative TEXT NOT NULL DEFAULT '',
                metric_delta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(issue_id) REFERENCES issues(id)
            );

            CREATE TABLE IF NOT EXISTS legacies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_issue_id INTEGER,                    -- 产生它的 issue（可空）
                modifiers TEXT NOT NULL DEFAULT '{}',  -- 各维度带符号百分比修正符 {"国库":10,"regions":{...},"armies":{...}}
                narrative_hint TEXT NOT NULL DEFAULT '',    -- 一句话说明（仅展示用，不喂 simulator）
                start_month INTEGER NOT NULL,               -- 绝对月 = year*12+period
                duration_months INTEGER NOT NULL DEFAULT 24,-- 时长；-1=永久
                status TEXT NOT NULL DEFAULT 'active',      -- active / expired / cleared
                clear_gate TEXT NOT NULL DEFAULT '{}',      -- 机器消除条件（gating.evaluate_gate 语法）；非空=靠程序判定消除而非时长
                legacy_key TEXT NOT NULL DEFAULT '',        -- 开局负面修正对应 opening_legacies.key，去重用
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_legacies_active
            ON legacies(status);

            CREATE INDEX IF NOT EXISTS idx_issues_active
            ON issues(kind, status, severity DESC);

            CREATE INDEX IF NOT EXISTS idx_issue_advances_issue
            ON issue_advances(issue_id, turn);

            CREATE TABLE IF NOT EXISTS classes (
                name TEXT NOT NULL,
                region_id TEXT NOT NULL DEFAULT '',
                population INTEGER NOT NULL,
                satisfaction INTEGER NOT NULL,
                leverage INTEGER NOT NULL,
                agenda TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (name, region_id)
            );

            CREATE INDEX IF NOT EXISTS idx_classes_region
            ON classes(region_id, name);

            CREATE TABLE IF NOT EXISTS event_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                cause TEXT NOT NULL DEFAULT '',
                process TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                sentiment TEXT NOT NULL DEFAULT 'neutral',
                importance INTEGER NOT NULL DEFAULT 3,
                tags TEXT NOT NULL DEFAULT '[]',
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                expires_turn INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(subject_type, subject_id, event_type, source_kind, source_id)
            );

            CREATE INDEX IF NOT EXISTS idx_event_memories_subject
            ON event_memories(subject_type, subject_id, turn);

            CREATE INDEX IF NOT EXISTS idx_event_memories_turn
            ON event_memories(turn, importance);

            CREATE INDEX IF NOT EXISTS idx_event_memories_expiry
            ON event_memories(expires_turn, turn);


            CREATE TABLE IF NOT EXISTS event_memory_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                excerpt TEXT NOT NULL DEFAULT '',
                locator TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(memory_id) REFERENCES event_memories(id) ON DELETE CASCADE,
                UNIQUE(memory_id, source_kind, source_id, locator)
            );

            CREATE INDEX IF NOT EXISTS idx_event_memory_sources_memory
            ON event_memory_sources(memory_id);

            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for column, definition in {
            "military_strength": "INTEGER NOT NULL DEFAULT 50",
            "cohesion": "INTEGER NOT NULL DEFAULT 50",
            "supply": "INTEGER NOT NULL DEFAULT 50",
            "last_action": "TEXT NOT NULL DEFAULT ''",
            "kind": "TEXT NOT NULL DEFAULT '敌国'",
            "aliases": "TEXT NOT NULL DEFAULT ''",
        }.items():
            self.ensure_column("powers", column, definition)
        self.ensure_column("armies", "owner_power", "TEXT NOT NULL DEFAULT 'ming'")
        self.ensure_column("armies", "troop_composition", "TEXT NOT NULL DEFAULT '{}'")
        self.ensure_column("regions", "controlled_by", "TEXT NOT NULL DEFAULT 'ming'")
        self.ensure_column("characters", "power_id", "TEXT NOT NULL DEFAULT 'ming'")
        self.ensure_column("characters", "location", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("characters", "origin", "TEXT NOT NULL DEFAULT 'preset'")
        self.ensure_column("characters", "archived", "INTEGER NOT NULL DEFAULT 0")
        self.conn.execute(
            """
            UPDATE characters
            SET origin='runtime'
            WHERE origin='preset'
              AND name IN (
                SELECT character_name FROM character_offices
                WHERE source IN (
                    '吏部任命', '吏部铨选任命', '诏书纳妃', '史实人物补档',
                    '皇帝确认背景补档', '名册外人物补档', '礼部选秀'
                )
                OR source LIKE '%补档%'
                OR source LIKE '%任命%'
                OR source LIKE '%纳妃%'
              )
            """
        )
        self.ensure_column("issues", "resolve_condition", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("issues", "fail_condition", "TEXT NOT NULL DEFAULT ''")
        # 玩家手动管理的 decree 局势：is_manual=1 标记由皇帝直接立项（非 LLM/事件池）；
        # duration_turns>0 时到期（origin_turn+duration_turns）自动撤销，无成功/失败奖励。
        self.ensure_column("issues", "is_manual", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("issues", "duration_turns", "INTEGER NOT NULL DEFAULT 0")
        # goal：皇帝给该局势定的目标/意图，喂给推演 simulator 据此逐月推进进度（对所有 issue 生效，玩家可改）。
        self.ensure_column("issues", "goal", "TEXT NOT NULL DEFAULT ''")
        # assignee：局势承办人/主责大臣。推演按其职掌、能力、状态判每月正负推进。
        self.ensure_column("issues", "assignee", "TEXT NOT NULL DEFAULT ''")
        # 承办人授权（皇帝批专款+生杀权后，承办人每月自主从专款推进，不必再下圣旨）：
        #   budget_pool=剩余专款万两（批复时累加，每月推演支取后递减；0=无专款）；
        #   budget_source=专款出库（'国库'/'内库'/''）；death_authority=专断之权(0/1)。
        self.ensure_column("issues", "budget_pool", "REAL NOT NULL DEFAULT 0")
        self.ensure_column("issues", "budget_source", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("issues", "death_authority", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "birth_year", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "historical_death_year", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "historical_death_month", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "debut_year", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "debut_month", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "status", "TEXT NOT NULL DEFAULT 'active'")
        self.ensure_column("characters", "status_reason", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("characters", "status_changed_turn", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("characters", "portrait_id", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("characters", "court_role", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("characters", "summary", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("characters", "aliases", "TEXT NOT NULL DEFAULT '[]'")
        self.ensure_column("characters", "diplomacy", "INTEGER NOT NULL DEFAULT 50")
        self.ensure_column("characters", "martial", "INTEGER NOT NULL DEFAULT 50")
        self.ensure_column("characters", "stewardship", "INTEGER NOT NULL DEFAULT 50")
        self.ensure_column("characters", "intrigue", "INTEGER NOT NULL DEFAULT 50")
        self.ensure_column("characters", "learning", "INTEGER NOT NULL DEFAULT 50")
        # 旧库五维回填：只在首次迁移执行一次（kv_store 打标）。此前「值=50 门控」
        # 每次启动都会覆写玩家恰调到 50 的数值，且回填后每次启动都白跑三遍 UPDATE。
        if not self.kv_get("five_dim_backfill_done"):
            self.conn.execute(
                """
                UPDATE characters
                SET diplomacy=MAX(0, MIN(100, ROUND((ability + loyalty) / 2.0))),
                    martial=MAX(0, MIN(100, ROUND((ability + courage) / 2.0))),
                    stewardship=ability,
                    intrigue=MAX(0, MIN(100, ROUND((ability + courage + (100 - integrity)) / 3.0))),
                    learning=ability
                WHERE diplomacy=50 AND martial=50 AND stewardship=50 AND intrigue=50 AND learning=50
                """
            )
            self.conn.execute(
                """
                UPDATE characters
                SET martial=MAX(0, MIN(100, ROUND((ability + courage) / 2.0)))
                WHERE martial=50
                """
            )
            self.conn.execute(
                """
                UPDATE characters
                SET stewardship=ability
                WHERE stewardship=50
                """
            )
            self.kv_set("five_dim_backfill_done", "1")
        # 步骤7：回合阶段（旧库迁移，schema 升级非 fallback）
        self.ensure_column("game_state", "turn_phase", "TEXT NOT NULL DEFAULT 'summoning'")
        # 结局：ended=1 时游戏终结；ending_status 为 context.ENDING_* 类型。
        self.ensure_column("game_state", "ended", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("game_state", "ending_status", "TEXT NOT NULL DEFAULT ''")
        # 密令推演进度列（result 留给承办人回报，sim_note 给推演写短进度/风险，互不覆盖）
        self.ensure_column("secret_orders", "sim_note", "TEXT NOT NULL DEFAULT ''")
        # 密令期限：0=无硬期限；到 due_turn 时自动转入待核议，由推演当月判 done/failed。
        self.ensure_column("secret_orders", "due_turn", "INTEGER NOT NULL DEFAULT 0")
        # 局势推进日志时间列：旧库只有 turn，新日志补 year/period 供推演按年月回看。
        self.ensure_column("issue_advances", "year", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_column("issue_advances", "period", "INTEGER NOT NULL DEFAULT 0")
        # fiscal_config 科目元数据列（数据驱动预算目录）：budget_role=fixed 的 base 项靠
        # account/direction/display 由 flows.compute_budget_lines 动态生成预算行；
        # dynamic 项（田赋/辽饷/盐税/商税/皇庄）走省级公式/皇庄专路，这三列留空。
        # offices 表存 court 授权 blob：{court_tools,agno_skills,chips} 的 json。
        # court tool 挂载 / agno skill 注入 / 前端 chip 全读这列；改授权＝UPDATE offices 这行，不必改设定文件。
        self.ensure_column("offices", "court_grant_json", "TEXT NOT NULL DEFAULT '{}'")
        self.ensure_column("fiscal_config", "budget_role", "TEXT NOT NULL DEFAULT 'fixed'")
        self.ensure_column("fiscal_config", "account", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("fiscal_config", "direction", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("fiscal_config", "display", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("fiscal_config", "sort_order", "INTEGER NOT NULL DEFAULT 9999")
        self.ensure_column("fiscal_config", "formula", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("fiscal_config", "basis", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("fiscal_config", "rate_unit", "TEXT NOT NULL DEFAULT ''")
        # economy_ledger 支出结构化标签：仅 extractor 抽出的 economy_moves 填这三列；
        # flows 月固定支出与所有收入留 NULL。purpose 受控枚举见 constants.ECONOMY_PURPOSES。
        self.ensure_column("economy_ledger", "purpose", "TEXT")
        self.ensure_column("economy_ledger", "target_kind", "TEXT")
        self.ensure_column("economy_ledger", "target_id", "TEXT")
        # 开局负面帝国修正：clear_gate(机器消除条件)、legacy_key(对应 opening_legacies.key，开局修正去重用)
        self.ensure_column("legacies", "clear_gate", "TEXT NOT NULL DEFAULT '{}'")
        self.ensure_column("legacies", "legacy_key", "TEXT NOT NULL DEFAULT ''")
        # 部门来源：preset(开局六部内阁) vs issue(玩家诏书新设衙门)，吏部抽屉/payload 区分用。
        self.ensure_column("offices", "origin", "TEXT NOT NULL DEFAULT 'preset'")
        # 章节记忆正文：event_type='chapter_summary' 用，存整段叙事章节（不受 outcome 80 字限）。
        self.ensure_column("event_memories", "body", "TEXT NOT NULL DEFAULT ''")
        # 后宫调教记录
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS consort_traits (
                name TEXT PRIMARY KEY,
                extra_skills TEXT NOT NULL DEFAULT '',
                extra_traits TEXT NOT NULL DEFAULT '',
                updated_turn INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 结局总结：每局结局触发时落一条（单 campaign 一库，turn 为主键，对齐 turn_reports）。
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ending_summary (
                turn INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                ending_status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                timeline TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._drop_regions_grain_security_column()
        self._migrate_region_grain_fiscal_fields()
        self._migrate_region_liao_xiang_li()
        # 军队软删除标记：撤销（manpower 归 0）的番号置 active=0，盘面/payload/前端读取层过滤掉，
        # 行仍留库可被「收复/重建」事件复活。旧档默认 active=1（满编军不受影响）。
        self.ensure_column("armies", "active", "INTEGER NOT NULL DEFAULT 1")
        # army_arms 升「军→兵种→装备」三级（主键加 troop_type）。老档主键是 (army_id,weapon_id)，
        # ensure_column 改不了主键，须重建表：旧持械行 troop_type 置 ''（视为未分兵种，玩家持械不丢）。
        self._migrate_army_arms_troop_type()
        self.conn.commit()
        self.init_fiscal_config()

    def _migrate_army_arms_troop_type(self) -> None:
        """army_arms 升三级（军→兵种→装备）：主键从 (army_id,weapon_id) 改成
        (army_id,troop_type,weapon_id)。老档主键不含 troop_type，ensure_column 改不了主键，
        须重建表搬数据（旧持械行 troop_type 置 ''＝未分兵种，玩家持械不丢）。已含 troop_type 列则跳过。"""
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(army_arms)").fetchall()}
        if not cols:
            return  # 表还没建（新库由 init 的 CREATE TABLE 直接建好三级）
        if "troop_type" in cols:
            return  # 已是三级，无需迁移
        self.conn.executescript(
            """
            ALTER TABLE army_arms RENAME TO army_arms_old;
            CREATE TABLE army_arms (
                army_id TEXT NOT NULL,
                troop_type TEXT NOT NULL DEFAULT '',
                weapon_id TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(army_id, troop_type, weapon_id),
                FOREIGN KEY(army_id) REFERENCES armies(id),
                FOREIGN KEY(weapon_id) REFERENCES weapons(id)
            );
            INSERT INTO army_arms (army_id, troop_type, weapon_id, qty, updated_at)
                SELECT army_id, '', weapon_id, qty, updated_at FROM army_arms_old;
            DROP TABLE army_arms_old;
            """
        )

    def _migrate_region_grain_fiscal_fields(self) -> None:
        """旧存档迁移：确保 regions.fiscal 带年度粮食产量与当前存粮字段。"""
        content_defaults = {
            region_id: {
                "grain_output": int((region.fiscal or {}).get("grain_output") or 0),
                "grain_stock": int((region.fiscal or {}).get("grain_stock") or 0),
            }
            for region_id, region in self.content.regions.items()
        }
        for row in self.conn.execute("SELECT id, fiscal FROM regions").fetchall():
            region_id = str(row["id"])
            try:
                fiscal = json.loads(str(row["fiscal"] or "{}"))
            except Exception:
                fiscal = {}
            if not isinstance(fiscal, dict):
                fiscal = {}
            defaults = content_defaults.get(region_id, {})
            changed = False
            for key in ("grain_output", "grain_stock"):
                if key in fiscal:
                    continue
                fiscal[key] = int(defaults.get(key, 0) or 0)
                changed = True
            if changed:
                self.conn.execute(
                    "UPDATE regions SET fiscal = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(fiscal, ensure_ascii=False), region_id),
                )

    def _migrate_region_liao_xiang_li(self) -> None:
        """旧存档迁移：liao_xiang 月额 → liao_xiang_li 亩率。"""
        content_defaults = {
            region_id: int((region.fiscal or {}).get("liao_xiang_li") or 0)
            for region_id, region in self.content.regions.items()
        }
        for row in self.conn.execute("SELECT id, fiscal FROM regions").fetchall():
            region_id = str(row["id"])
            try:
                fiscal = json.loads(str(row["fiscal"] or "{}"))
            except Exception:
                fiscal = {}
            if not isinstance(fiscal, dict):
                fiscal = {}
            changed = False
            if "liao_xiang_li" not in fiscal:
                old_monthly = int(fiscal.get("liao_xiang") or 0)
                guan_min_tian = int(fiscal.get("guan_min_tian") or 0)
                if old_monthly > 0 and guan_min_tian > 0:
                    fiscal["liao_xiang_li"] = round(old_monthly * 10000 * 12 / guan_min_tian)
                else:
                    fiscal["liao_xiang_li"] = int(content_defaults.get(region_id, 0) or 0)
                changed = True
            if "liao_xiang" in fiscal:
                fiscal.pop("liao_xiang", None)
                changed = True
            if changed:
                self.conn.execute(
                    "UPDATE regions SET fiscal = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(fiscal, ensure_ascii=False), region_id),
                )

    def _drop_regions_grain_security_column(self) -> None:
        """旧存档迁移：regions.grain_security → fiscal.grain_stock，然后删旧列。"""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(regions)").fetchall()}
        if "grain_security" not in columns:
            return
        for row in self.conn.execute("SELECT id, fiscal, grain_security FROM regions").fetchall():
            try:
                fiscal = json.loads(str(row["fiscal"] or "{}"))
            except Exception:
                fiscal = {}
            fiscal.setdefault("grain_stock", int(row["grain_security"] or 0))
            self.conn.execute(
                "UPDATE regions SET fiscal = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(fiscal, ensure_ascii=False), str(row["id"])),
            )
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=OFF")
        try:
            self.conn.executescript(
                """
                CREATE TABLE regions__new (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    population INTEGER NOT NULL,
                    public_support INTEGER NOT NULL,
                    unrest INTEGER NOT NULL,
                    natural_disaster TEXT NOT NULL,
                    human_disaster TEXT NOT NULL,
                    registered_land INTEGER NOT NULL,
                    hidden_land INTEGER NOT NULL,
                    tax_per_turn INTEGER NOT NULL,
                    gentry_resistance INTEGER NOT NULL,
                    military_pressure INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    controlled_by TEXT NOT NULL DEFAULT 'ming',
                    fiscal TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(controlled_by) REFERENCES powers(id)
                );

                INSERT INTO regions__new
                (id, name, kind, population, public_support, unrest, natural_disaster, human_disaster,
                 registered_land, hidden_land, tax_per_turn, gentry_resistance, military_pressure,
                 status, controlled_by, fiscal, updated_at)
                SELECT id, name, kind, population, public_support, unrest, natural_disaster, human_disaster,
                       registered_land, hidden_land, tax_per_turn, gentry_resistance, military_pressure,
                       status, controlled_by, fiscal, updated_at
                FROM regions;

                DROP TABLE regions;
                ALTER TABLE regions__new RENAME TO regions;
                """
            )
            self.conn.commit()
        finally:
            self.conn.execute("PRAGMA foreign_keys=ON")
