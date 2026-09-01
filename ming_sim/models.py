"""数据类：游戏实体与状态容器。L0 叶子模块。

CourtContext 的 state/db 注解用字符串前向引用，避免 import db.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Literal

if TYPE_CHECKING:
    from ming_sim.db import GameDB

from ming_sim.constants import ECONOMY_ACCOUNTS


@dataclass
class ChatResult:
    action: str
    next_minister: str = ""
    refresh_ministers: List[str] = field(default_factory=list)


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    max_tokens: int = 8000
    timeout_seconds: float = 180.0  # 总超时（整次请求上限）
    connect_timeout_seconds: float = 60.0  # 建连超时
    read_timeout_seconds: float = 120.0  # 流式下两次 socket 读之间的最大间隔（chunk 间隔超此判卡死）
    thinking_level: str = ""  # 空=沿用旧逻辑；否则原样传给 reasoning_effort
    advanced_model: str = ""  # 空=fallback model；非空=推演/打分专用更强模型（如 deepseek-reasoner / gpt-5）
    advanced_base_url: str = ""  # 空=复用主 base_url；非空=advanced 角色专用网关
    advanced_api_key: str = ""  # 空=复用主 api_key；非空=advanced 角色专用 key
    advanced_thinking_level: str = ""  # 空=沿用旧逻辑；advanced 角色原样传给 reasoning_effort


@dataclass
class Character:
    name: str
    office: str
    office_type: str
    faction: str
    aliases: List[str]
    personal_skills: List[str]
    loyalty: int
    ability: int
    integrity: int
    courage: int
    style: str
    power_id: str
    diplomacy: int = 50  # 外交
    martial: int = 50  # 军事
    stewardship: int = 50  # 管理
    intrigue: int = 50  # 谋略
    learning: int = 50  # 学识
    location: str = ""
    birth_year: int = 0  # 历史生年（公历，0=未填）
    historical_death_year: int = 0  # 历史卒年（公历，0=未填）
    historical_death_month: int = 0  # 1-12，0=未指定
    debut_year: int = 0  # 历史登场年（公历，0=开局即在场）
    debut_month: int = 0  # 1-12，0=不限月
    status: Literal["active", "offstage", "dismissed", "imprisoned", "exiled", "retired", "dead"] = "active"
    summary: str = ""  # 人物简介，后宫/大臣均有
    portrait_id: str = ""  # 头像文件标识：空=无专属；"minister_pool_3"=用第3号预设头像


@dataclass
class Event:
    id: str
    title: str
    kind: str
    summary: str
    urgency: int
    severity: int
    credibility: int
    interests: List[str]
    audiences: List[str]
    resolve_condition: str = ""
    fail_condition: str = ""
    trigger_year: int = 0   # 历史锚定触发年（公历，0=非历史锚定，靠 trigger_gate）
    trigger_month: int = 0  # 1-12，0=年内任意月
    is_historical: Optional[bool] = None  # 是否史实锚定情势，喂 simulator 决定浮现策略；JSON 不填则缺省=trigger_year>0
    trigger_end_year: int = 0   # 候选窗口结束年（0=不设上限）
    trigger_end_month: int = 0  # 候选窗口结束月（0=年内任意月）
    precondition: str = ""  # 触发前提的人话说明，喂 simulator 由 LLM 判定（叙事背景+结果烈度/走向，可列结果分档）；不走程序求值（触发与否的程序闸看 require/trigger_gate）
    require: Dict[str, object] = field(default_factory=dict)  # 结构化触发前提（布尔树/扁平 dict，见 gating.evaluate_gate）；空=无可证伪前提（历史既定型）。require 不过则 node 不进候选/不触发
    event_type: Literal["situation", "node", "ending"] = "situation"
    trigger_gate: Dict[str, str] = field(default_factory=dict)  # seed 候选门槛：{metric: 比较式}，全满足才进候选
    auto_trigger: bool = False  # True=gate 达标即由程序硬立项，绕过 LLM 因果判定（不进候选池等 extractor 决定）
    # 以下为可选「精调 issue 字段」：原 opening_crises 那种手调危机用，立项时 event_to_issue 优先读这些，
    # 缺省（0/空）则按 severity/kind 自动推导。合并 opening_crises → seed_events 后承接其手调值。
    bar_value: int = 0                                            # 0=自动推导
    bar_good_meaning: str = ""
    bar_bad_meaning: str = ""
    issue_inertia: int = 0                                        # 立项时初始 inertia（默认 0=不漂；要每月漂移就在 seed/event 里显式填）
    stage_text: str = ""                                          # issue 阶段文案（空=用 summary）
    region_hint: str = ""
    issue_tags: List[str] = field(default_factory=list)           # 空=用 [kind]
    ongoing_effects: Dict[str, object] = field(default_factory=dict)
    effect_on_resolve: Dict[str, object] = field(default_factory=dict)
    effect_on_fail: Dict[str, object] = field(default_factory=dict)


@dataclass
class Faction:
    name: str
    satisfaction: int
    leverage: int
    agenda: str


@dataclass
class SocialClass:
    """阶级人口：朝堂外的社会基本盘。
    region_id="" 表示全国汇总；非空表示该省切片（key 与 regions.id 对应）。
    机制：lev 高 + sat 低 → 易触发该省/该阶级骚乱事件，由 LLM 在推演中判定。
    """
    name: str            # 农民/士绅/官僚/军户/商人/匠户/宗藩
    region_id: str       # "" = 全国汇总；否则匹配 regions.id
    population: int      # 万人（粗估，全国汇总=各省合计的参考值）
    satisfaction: int    # 0-100
    leverage: int        # 0-100
    agenda: str          # 一句话诉求


@dataclass
class Region:
    id: str
    name: str
    kind: str
    population: int
    public_support: int
    unrest: int
    natural_disaster: str
    human_disaster: str
    registered_land: int   # 在册田亩（万亩）＝黄册登记可征税田＝官民田+藩王庄田+皇庄之和
    hidden_land: int       # 隐田（万亩）＝账外逃赋田：官民田被缙绅诡寄/飞洒/漏籍 ＋ 藩王超额侵占的民田。独立于在册，清丈即转入在册官民田。不含藩王钦赐免税庄田/皇庄
    tax_per_turn: int
    gentry_resistance: int
    military_pressure: int
    status: str
    controlled_by: str
    fiscal: dict = field(default_factory=dict)
    on_restore: dict = field(default_factory=dict)
    # fiscal JSON 字段说明（万亩/万两/0-100）：
    # huang_tian    皇庄（万亩），产出→内库，仅北直隶有
    # wang_tian     藩王庄田（万亩），免税，禄米→国库支出
    # guan_min_tian 官民田（万亩），田赋→国库
    # liao_xiang_li 辽饷亩率（毫/亩/年），按官民田摊派
    # salt_tax      盐税月基数（万两），产盐省才>0
    # commerce_tax  商税月基数（万两）
    # corruption    腐败度 0-100，影响解运比
    # on_restore    收复时（controlled_by 非 ming → ming）覆盖到主字段的预置盘面


@dataclass
class Army:
    id: str
    name: str
    station: str
    theater: str
    commander: str
    controller: str
    troop_type: str
    troop_composition: dict
    manpower: int
    maintenance_per_turn: int
    supply: int
    morale: int
    training: int
    equipment: int
    arrears: int
    mobility: int
    loyalty: int
    status: str
    owner_power: str
    arms: list = field(default_factory=list)  # 开局持械 [{troop_type, weapon, qty}]，seed 写 army_arms


@dataclass
class Building:
    id: str
    region_id: str
    name: str
    category: str          # 财政/军事/民生/科技/交通/内廷
    level: int             # 规模 1-5
    condition: int         # 完好 0-100，产出折算系数
    maintenance: int       # 每月维护费 万两
    risk: int              # 0-100
    output_metric: str     # 国库/内库/军备/民心 或 "" 表示纯叙事
    output_amount: int     # 每月产出量
    status: str


@dataclass
class Power:
    id: str
    name: str
    kind: str
    leader: str
    stance: str
    leverage: int
    satisfaction: int
    military_strength: int
    cohesion: int
    supply: int
    agenda: str
    status: str
    last_action: str = "尚无新动"
    aliases: str = ""


@dataclass
class OpeningLegacy:
    """开局即存在的负面帝国修正：永久 legacy（duration=-1），靠 clear_gate 程序判定消除。
    不立 issue、不进推演。见 content/opening_legacies.json 与 db.sync_opening_legacies。"""
    key: str
    name: str
    modifiers: Dict[str, object]
    narrative_hint: str
    clear_gate: Dict[str, object]  # gate DSL：布尔树 / 扁平 dict，见 gating.evaluate_gate
    clear_narrative: str = ""


@dataclass
class PresetDepartment:
    """可由皇帝诏书新设的预设衙门。LLM 新立局势带上 key→程序立项时用本预设覆盖 issue 字段
    （题材/条件/月数/一次性 effect），结案落 offices 表并按 modifiers 挂永久 legacy。
    见 content/preset_departments.json。表外自创部门不走此池、无 modifiers。
    一次性奖励/惩罚走 effect_on_resolve/effect_on_fail；建立/失败条件预写，符合史实阻力。"""
    key: str
    name: str
    category: str
    authority_scope: str
    power: int
    responsibility: int
    corruption_risk: int
    effect_summary: str
    modifiers: Dict[str, object]
    theme: str                                  # issue 题材（八枚举之一）
    expected_months: int                        # 预计月数（定 inertia / 难度）
    bar_value: int                              # 立项起步进度
    stage_text: str                             # issue 起步阶段文案
    resolve_condition: str                      # 怎么算建成
    fail_condition: str                         # 怎么算黄
    effect_on_resolve: Dict[str, object]        # 一次性建成奖励（含 departments:create）
    effect_on_fail: Dict[str, object]           # 一次性失败代价
    requires: List[str] = field(default_factory=list)  # 前置衙门 key；空=根节点


@dataclass
class PresetTechnology:
    """可由皇帝诏书推动的预设科技。LLM 新立局势带上 key→程序立项时用本预设覆盖 issue 字段，
    结案落 technologies 表（无月度产出）并按 modifiers 挂永久 legacy。
    见 content/preset_technologies.json。一次性奖励/惩罚走 effect_on_resolve/effect_on_fail。"""
    key: str
    name: str
    category: str
    effect_summary: str
    modifiers: Dict[str, object]
    theme: str
    expected_months: int
    bar_value: int
    stage_text: str
    resolve_condition: str
    fail_condition: str
    effect_on_resolve: Dict[str, object]
    effect_on_fail: Dict[str, object]
    requires: List[str] = field(default_factory=list)  # 前置科技 key；空=根节点。立项时强制校验前置全研成（_unmet_tech_prereqs）
    default_unlocked: bool = False                     # 新档开局即已研成并 seed 入 technologies


@dataclass
class GameState:
    year: int = 1627
    period: int = 10
    turn: int = 1
    turn_phase: Literal["summoning", "reviewing", "awaiting_decision", "issued"] = "summoning"
    ended: bool = False  # 结局已触发：游戏终结，拒绝继续召见/结算
    ending_status: str = ""  # 结局类型（context.ENDING_*），ended=True 时有值
    metrics: Dict[str, float] = field(
        default_factory=lambda: {
            "国库": 320,
            "内库": 440,
            "民心": 50,
            "皇威": 20,
        }
    )
    log: List[str] = field(default_factory=list)

    def clamp(self) -> None:
        for key, value in list(self.metrics.items()):
            if key in ECONOMY_ACCOUNTS:
                self.metrics[key] = float(value)
            else:
                self.metrics[key] = max(0, min(100, value))

    def next_period(self) -> None:
        self.turn += 1
        self.period += 1
        if self.period > 12:
            self.period = 1
            self.year += 1


@dataclass
class CourtContext:
    state: "GameState"
    db: "GameDB"  # 用前向注解避免 import db.py 造成环
    previous_summary: str = ""


def period_label(year: int, month: int) -> str:
    return f"{year}年{month}月"


def monthly_amount(amount: int) -> int:
    # 全盘已按月度：base/maint/tax 都是月值，不再除 3。保留函数仅为兼容旧调用点（恒等）。
    return max(0, int(amount))
