"""Agno Agent 执行与工厂（非大臣类）：run_agent_*、parse_agent_json、
诏书润色/月末推演/打分提取/JSON 修复 agent。L5。

通过 bind_content() 注入 GameContent（取提示词）。
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.db.sqlite import SqliteDb

from ming_sim.assets import strip_json_fence
from ming_sim.constants import TURN_UNIT
from ming_sim.content import GameContent
from ming_sim.exceptions import LLMContractError, LLMUnavailable
from ming_sim.llm_config import agent_sampling_settings, for_role as _llm_for_role, is_minimax_base_url
from ming_sim.llm_contract import abort_llm_contract, fail_if_llm_error
from ming_sim.llm_model import create_chat_model, extract_agent_text, llm_unavailable_from_error
from ming_sim.models import GameState, LLMConfig
from ming_sim.token_stats import record_stream_metrics, tlog, use_agno_metrics

_content: Optional[GameContent] = None
_THINKING_STREAM_CHAR_LIMIT = max(0, int(os.environ.get("MING_SIM_THINKING_STREAM_LIMIT", "600") or "0"))
_MINIMAX_SHORT_THINKING_PROMPT = (
    "【MiniMax 推演思考约束】\n"
    "若启用 thinking/reasoning，请极短思考：只列必要因果链，不复述题目、盘面、系统规则或历史常识；"
    "不要写英文分析；不要自我解释“我将如何回答”；思考控制在约 200 个中文字内。"
    "最终正文仍须完整遵守月末奏疏格式与内容要求。"
)
_HITL_PROMPT = """## 4. 遇阻反馈与动态纠偏（HITL 决策点，最多 5 个）

奏章正文写完之后，若本{{TURN_UNIT}}推演中出现承办人已经努力但卡住的具体阻力，在奏章末尾追加决策块，交皇帝亲裁，用来**动态纠偏**：补资源、补授权、换路径、换承办人、强推或暂缓。决策块是承办人向皇帝反馈“臣办到此处，卡在此处，请陛下改令”的二选一/三选一；不是叙事，也不是把已成定局的事再问一遍。

**产出条数由 `simulator_payload.hitl_min_decisions` 定上限**：
- `hitl_min_decisions` ≥ 1：本{{TURN_UNIT}}**最多产出这么多个**决策块。优先用于长期局势/诏书执行/密令核议遇到真实阻力后的反馈纠偏；若没有承办人反馈的具体卡点或亲裁级分岔，可以不出。不要为了凑数把寻常政务、中等张力或已成定局之事做成抉择。

够格的典型纠偏点：承办人缺银缺粮需追加专款或改拨来源；地方/部院掣肘需授专断之权或改派承办人；在朝大臣阻挠需皇帝决定拿问、申饬或暂避；工程/新法遇料荒、试验失败需改路线或放缓；军务遇欠饷、援兵不至、敌军反扑需调兵/撤守/议款；密令风声走漏需收网、放线或切断。大战和、迁都弃地、赦杀重臣、外部密约等传统重大抉择仍可出，但也要写成“当前阻力逼到非皇帝不可纠偏”的反馈。寻常政务、已在诏书里定了且没有新阻力的事不要做成抉择。总数任何情况下不超过 5 个。

长期局势带 `目标` 且有承办人时，承办人本{{TURN_UNIT}}会主动想办法推进；若他在奏章中反馈了具体阻力，且该阻力已经超出承办人权限/钱粮/人手可解范围，就应优先考虑产出 HITL。HITL 的 `context` 必须包含三件事：承办人本{{TURN_UNIT}}已试过的办法、卡住的具体阻力、为什么需要皇帝改令纠偏。不要泛泛说“局势复杂”。

人物类抉择必须先查 `court_roster.status/location`：`active` 才是在朝可被新拿问/罢官；`dismissed`=已罢黜，`imprisoned`=已下狱，`exiled`=已流放，`retired`=已致仕，`dead`=已故。已非 `active` 的人物不得再产出“拿问/下狱/罢官/发配”这类重复抉择；只有确有新分岔时，才可问“追赃、会审定罪、处置党羽、赦免/处死”等下一步，且 context 必须明写其当前状态。

格式（严格 JSON，一桩一块，最多 5 块，每块独立一行的 `<<DECISION>>` 与 `<<END>>` 包裹）：

```
<<DECISION>>
{"title":"≤12字纠偏名","context":"40-90字写承办人已试办法、具体卡点、为何须皇帝改令","options":[{"label":"纠偏旨意一","hint":"方向性后果倾向"},{"label":"纠偏旨意二","hint":"方向性后果倾向"}]}
<<END>>
```

- `options` 给 **2-3 个**互斥选项；`label` 是皇帝可下的纠偏旨意（追加专款、授/不授专断、换人、强推、暂缓、改路线、收网等），`hint` 只给**方向性倾向**（如「推进加速，然耗内帑且激怒部院」），**不写具体数值、不写 bar/±N**。
- `context` 写清承办人反馈的阻力与请裁缘由，别复述整章正文。
- 决策块只放奏章**最末尾**，放在整份奏章正文（最后一章）之后；块外不再有正文。
- 决策块必须从本{{TURN_UNIT}}盘面/诏书/在办局势/候选情势/密令日志中的真实阻力自然长出，**不得为凑决策点硬造**清单外的新危机；上限只限制最多写几处，不要求写满。"""


def bind_content(content: GameContent) -> None:
    global _content
    _content = content


def _ctx() -> GameContent:
    if _content is None:
        raise RuntimeError("agents.bind_content() 未调用：GameContent 未注入。")
    return _content


def _render_hitl_prompt(prompt: str, simulator_payload: Optional[Dict[str, object]]) -> str:
    raw_min_decisions = (simulator_payload or {}).get("hitl_min_decisions", 0)
    try:
        min_decisions = int(raw_min_decisions)
    except (TypeError, ValueError):
        min_decisions = 0
    hitl_prompt = _HITL_PROMPT.replace("{{TURN_UNIT}}", TURN_UNIT) if min_decisions > 0 else ""
    return prompt.replace("{{HITL}}", hitl_prompt)


# 调试开关：MING_SIM_DUMP_LLM=1 时把每次 agno 调用真实送进 LLM 的 system/user/assistant
# 全文落盘到 scripts/runs/llm_dump_<pid>.log。从 RunOutput.messages 取（=实际 payload，非重建）。
_DUMP_LLM = os.environ.get("MING_SIM_DUMP_LLM", "").strip() in ("1", "true", "yes")
_DUMP_PATH = f"scripts/runs/llm_dump_{os.getpid()}.log"


def _dump_llm_messages(output: Any, tag: str, agent: Optional[Agent] = None) -> None:
    """把这次 run 的完整 messages（含 system prompt）追加写盘。仅 _DUMP_LLM 开时生效。

    非流式：output 即 RunOutput，带 .messages。
    流式：终结事件 RunCompletedEvent 无 .messages，改从 agent.get_last_run_output() 取。"""
    if not _DUMP_LLM:
        return
    msgs = getattr(output, "messages", None)
    if not msgs and agent is not None:
        try:
            last = agent.get_last_run_output()
            msgs = getattr(last, "messages", None)
        except Exception:  # noqa: BLE001 — dump 是调试旁路，任何异常都不该断结算
            msgs = None
    if not msgs:
        return
    lines = [f"\n{'='*80}\n[DUMP] tag={tag}  共 {len(msgs)} 条 message\n{'='*80}"]
    for i, m in enumerate(msgs):
        role = getattr(m, "role", "?")
        content = getattr(m, "content", "")
        if content is None:
            content = ""
        lines.append(f"\n----- #{i} role={role} ({len(str(content))} 字) -----\n{content}")
        # 工具调用也带上
        tcalls = getattr(m, "tool_calls", None)
        if tcalls:
            lines.append(f"\n  [tool_calls] {tcalls}")
    try:
        with open(_DUMP_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        tlog(f"[{tag}] LLM messages 已 dump → {_DUMP_PATH}")
    except OSError as e:
        tlog(f"[{tag}] dump 写盘失败：{e}")


def run_agent_text(agent: Agent, prompt: str, tag: str) -> str:
    """非流式跑 agent，返回最终完整文本。
    extractor/sanitizer 这类要严格 JSON 的场合用——避免流式 buffer 把 LLM 偶发重发段累加成畸形。

    token 记账走 agno RunMetrics（与流式大臣同口径，含 cache_read/write）：dashscope 原生
    usage 不报 cached_tokens，靠 monkeypatch 抓只能得 0；agno metrics 能聚合出缓存命中。
    用 use_agno_metrics 关掉本次的 monkeypatch 原生记账，避免 prompt/completion 双计。"""
    tlog(f"[{tag}] 开始非流式推演（等待完整响应）")
    t0 = time.monotonic()
    try:
        with use_agno_metrics():
            output = agent.run(prompt)
    except LLMUnavailable:
        raise
    except Exception as error:
        # 超时（read 20s）/ 连接失败转成 LLMUnavailable，上层据此提示用户而非静默兜底。
        raise llm_unavailable_from_error(error, tag) from error

    _dump_llm_messages(output, tag)
    text = extract_agent_text(output)
    model_id = getattr(getattr(agent, "model", None), "id", None) or "nonstream"
    record_stream_metrics(str(model_id), getattr(output, "metrics", None), caller_tag=tag)
    tlog(f"[{tag}] 完成，{len(text)} 字，用时 {time.monotonic() - t0:.1f}s")
    return text

_HISTORIAN_PROMPT = """你是一名为《明史》修撰本纪的后世史官。
大明王朝刚刚迎来了它的终局。你将获得该朝代（本次游戏）历年的大事纪要（Game Log）、最终的各项国家指标（国库、内库、民心、皇威等）以及最终结局状态。
你需要用半文言半白话（类似《明史·本纪》风格，但现代人易读）为当朝皇帝撰写一篇“本纪”式的史书总结。

要求：
1. **庙号与谥号**：根据皇帝的最终表现（昏君、明君、亡国之君等），为他上一个【庙号】（如明X宗，若亡国可不上庙号）和【谥号】。
2. **总评**：一两百字高度概括其执政生涯的基调。
3. **大事记摘要**：结合你收到的历年大事历（Log），用史家笔法点出他任内的关键政策、战争、党争或荒唐行为。不要堆砌流水账，要挑出最能代表他执政风格的重点。
4. **结局定格**：描述他最终迎来的结局（如流寇破城自缢、中兴明室、大业未半而中道崩殂等）。
5. **赞曰**：模仿《明史》“赞曰”格式，在最后给出一段 50-100 字的精辟论断。

输出格式：直接输出史书内容，无需任何额外致辞。开头第一行须为：“庙号：xxx 谥号：xxx”。
"""

def write_ming_history(
    llm_config: LLMConfig,
    state: GameState,
) -> str:
    from ming_sim.context import ENDING_LABELS
    model = create_chat_model(llm_config)
    agent = Agent(
        model=model,
        instructions=[_HISTORIAN_PROMPT],
        markdown=False,
    )

    year = state.year
    period = state.period
    status = state.ending_status
    label = ENDING_LABELS.get(status, "未知结局")
    metrics = ", ".join(f"{k}: {v}" for k, v in state.metrics.items())
    logs = "\n".join(state.log[-50:])  # 截取最后50条防止过长
    if not logs:
        logs = "史籍散佚，无明文记载。"

    user_prompt = (
        f"在位终点：{year}年{period}月\n"
        f"最终结局：{label} ({status})\n"
        f"国家关键指标：{metrics}\n\n"
        f"历年大事记（摘录）：\n{logs}\n\n"
        f"请基于以上资料，为这位大明皇帝（玩家）撰写《明史·本纪》。"
    )

    try:
        res = agent.run(user_prompt)
        text = extract_agent_text(res)
        _dump_llm_messages(res, "historian_agent")
        return text.strip()
    except Exception as e:
        return f"《明史》编纂失败：{e}"


def run_agent_stream_text(
    agent: Agent,
    prompt: str,
    tag: str,
    on_thinking: Optional[Callable[[str], None]] = None,
    on_text: Optional[Callable[[str], None]] = None,
) -> str:
    """流式跑 agent，按事件实时打到 stdout（带毫秒时间戳），最终返回拼合后的纯文本。

    on_thinking(chunk): 每次思考片段到达时回调（可选）。
    on_text(chunk): 每次正文增量到达时回调（可选）。
    """
    tlog(f"[{tag}] 开始流式推演（首字到达前可能等几秒）")
    pieces: List[str] = []
    final_output = None
    last_print = time.monotonic()
    chunk_buf: List[str] = []
    chars_since_flush = 0
    try:
        stream = agent.run(prompt, stream=True, stream_events=True)
    except TypeError:
        tlog(f"[{tag}] 当前 agno 不支持 stream，退回普通 run")
        text = extract_agent_text(agent.run(prompt))
        if on_text:
            on_text(text)
        return text

    reasoning_buf: List[str] = []
    reasoning_chars_since_flush = 0
    reasoning_last_print = time.monotonic()
    reasoning_streamed_chars = 0
    tool_calls = 0

    def _events():
        # 取下一个流式 event 时把 httpx ReadTimeout / openai APITimeoutError（chunk 间隔
        # 超 20s 判卡死）等转成 LLMUnavailable，让上层 except LLMUnavailable 识别并提示用户。
        it = iter(stream)
        while True:
            try:
                yield next(it)
            except StopIteration:
                return
            except LLMUnavailable:
                raise
            except Exception as error:
                raise llm_unavailable_from_error(error, f"{tag} 流式推演") from error

    for event in _events():
        ev_type = type(event).__name__
        # 工具调用事件：记日志 + 把「正在查 X」作为思考片段推给前端
        if ev_type == "ToolCallStartedEvent":
            tool = getattr(event, "tool", None)
            tname = getattr(tool, "tool_name", "?") if tool else "?"
            targs = getattr(tool, "tool_args", {}) if tool else {}
            tool_calls += 1
            tlog(f"[{tag}/工具] 调用 {tname}({targs})")
            if on_thinking:
                on_thinking(f"\n〔查阅 {tname} {targs}〕\n")
            continue
        if ev_type == "ToolCallCompletedEvent":
            tool_res = getattr(event, "tool", None)
            tres = str(getattr(tool_res, "result", "") or "")[:200] if tool_res else ""
            if tres:
                tlog(f"[{tag}/工具结果] {tres!r}")
            continue
        rdelta = getattr(event, "reasoning_content", None)
        if isinstance(rdelta, str) and rdelta:
            reasoning_buf.append(rdelta)
            reasoning_chars_since_flush += len(rdelta)
            now = time.monotonic()
            if reasoning_chars_since_flush >= 120 or (now - reasoning_last_print) >= 1.5:
                merged = "".join(reasoning_buf)
                tlog(f"[{tag}/思考] {merged.replace(chr(10), ' ⏎ ')[-200:]}")
                if on_thinking and reasoning_streamed_chars < _THINKING_STREAM_CHAR_LIMIT:
                    remaining = _THINKING_STREAM_CHAR_LIMIT - reasoning_streamed_chars
                    chunk = merged[:remaining]
                    if chunk:
                        on_thinking(chunk)
                        reasoning_streamed_chars += len(chunk)
                reasoning_buf.clear()
                reasoning_chars_since_flush = 0
                reasoning_last_print = now
        is_terminal = (
            (hasattr(event, "is_final") and getattr(event, "is_final", False))
            or ev_type in ("RunOutput", "RunCompletedEvent")
        )
        if ev_type == "RunErrorEvent":
            raise LLMUnavailable(
                f"{tag} 流式调用失败：{getattr(event, 'content', None)}",
                code="llm_stream_error",
                provider_message=str(getattr(event, "content", None) or ""),
            )
        if is_terminal:
            final_output = event
            continue
        delta = getattr(event, "content", None)
        if isinstance(delta, str) and delta:
            pieces.append(delta)
            chunk_buf.append(delta)
            chars_since_flush += len(delta)
            if on_text:
                on_text(delta)
            now = time.monotonic()
            if chars_since_flush >= 80 or (now - last_print) >= 1.0:
                merged = "".join(chunk_buf).replace("\n", " ⏎ ")
                tlog(f"[{tag}] …{merged[-160:]}")
                chunk_buf.clear()
                chars_since_flush = 0
                last_print = now

    if reasoning_buf:
        merged = "".join(reasoning_buf)
        tlog(f"[{tag}/思考] {merged.replace(chr(10), ' ⏎ ')[-200:]}")
        if on_thinking and reasoning_streamed_chars < _THINKING_STREAM_CHAR_LIMIT:
            remaining = _THINKING_STREAM_CHAR_LIMIT - reasoning_streamed_chars
            chunk = merged[:remaining]
            if chunk:
                on_thinking(chunk)
                reasoning_streamed_chars += len(chunk)
    if chunk_buf:
        merged = "".join(chunk_buf).replace("\n", " ⏎ ")
        tlog(f"[{tag}] …{merged[-160:]}")

    streamed = "".join(pieces).strip()
    if streamed:
        text = streamed
        fail_if_llm_error(text, "LLM 调用")
    elif final_output is not None:
        text = extract_agent_text(final_output)
        if not text:
            abort_llm_contract(tag, "流式终结事件没有正文 content", "")
    else:
        abort_llm_contract(tag, "流式无内容且无终结事件", "")
    tlog(f"[{tag}] 完成，{len(text)} 字，工具调用 {tool_calls} 次")
    # 流式 openai response 无 .usage，monkeypatch 抓不到；从终结事件 metrics 补记 token。
    _dump_llm_messages(final_output, tag, agent=agent)
    if final_output is not None:
        metrics = getattr(final_output, "metrics", None)
        model_id = getattr(getattr(agent, "model", None), "id", None) or "stream"
        record_stream_metrics(str(model_id), metrics, caller_tag=tag)
    return text


def parse_agent_json(raw: str, stage: str) -> Dict[str, Any]:
    text = strip_json_fence(raw)
    # 试 1：原文直解
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    # 试 2：截 {...} 最外层再解
    if data is None:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            abort_llm_contract(stage, "没有返回 JSON object", raw)
        snippet = text[start : end + 1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            data = None
        # 试 3：净化 control char（\r\v\f\x00-\x1f 等）后再解
        if data is None:
            cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", snippet)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                data = None
        # 试 4：截取首个合法平衡的 {...} 子串（防 LLM 重发拼接）
        if data is None:
            depth = 0
            in_str = False
            esc = False
            best_end = -1
            for i, ch in enumerate(snippet):
                if esc:
                    esc = False
                    continue
                if ch == "\\" and in_str:
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        best_end = i
                        break
            if best_end > 0:
                first_block = snippet[: best_end + 1]
                first_block = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", first_block)
                try:
                    data = json.loads(first_block)
                except json.JSONDecodeError as error:
                    raise LLMContractError(
                        f"{stage} 输出不是合法 JSON：{error}\n原始输出：{raw[:800]}"
                    ) from error
            else:
                raise LLMContractError(
                    f"{stage} 输出不是合法 JSON\n原始输出：{raw[:800]}"
                )
    if not isinstance(data, dict):
        abort_llm_contract(stage, "顶层必须是 JSON object", raw)
    return data


def create_decree_writer_agent(llm_config: LLMConfig, agno_db: SqliteDb) -> Agent:
    # 一次性 agent：add_history_to_context=False，无需持久化 → 不传 db，免得每次往
    # <db>.emperor.db 的 agno_sessions 累积 runs 撑爆存档。agno_db 仅保留以兼容调用方。
    del agno_db
    return Agent(
        name="诏书润色官",
        id="decree-writer",
        model=create_chat_model(llm_config, temperature=0.2, top_p=0.2, max_tokens=max(1200, llm_config.max_tokens)),
        instructions=[_ctx().game_world_prompt, _ctx().decree_writer_prompt],
        add_history_to_context=False,
        markdown=False,
    )


def _is_cols_rows_table(v: object) -> bool:
    """判断某字段是否 {cols,rows} 二维表（可转 TSV）。"""
    return isinstance(v, dict) and set(v.keys()) == {"cols", "rows"}


_TSV_COL_LABELS: Dict[str, Dict[str, str]] = {
    "regions": {
        "name": "地区", "kind": "类型", "population": "人口", "public_support": "民心",
        "unrest": "动乱", "natural_disaster": "天灾", "human_disaster": "人祸",
        "registered_land": "在册田", "hidden_land": "隐田", "tax_per_turn": "月税",
        "gentry_resistance": "士绅阻力", "military_pressure": "军事压力",
        "status": "状态", "controlled_by": "控制", "guan_min_tian": "官民田",
        "wang_tian": "藩王庄田", "huang_tian": "皇庄", "tian_fu_li": "田赋亩率",
        "liao_xiang_li": "辽饷亩率", "salt_tax": "盐税", "commerce_tax": "商税",
        "grain_output": "粮产", "grain_stock": "余粮", "corruption": "腐败",
        "fiscal": "财政JSON",
    },
    "armies": {
        "name": "军队", "station": "驻地", "theater": "战区", "commander": "统帅",
        "controller": "主管", "troop_type": "兵种", "troop_composition": "编制", "manpower": "兵力",
        "maintenance_per_turn": "月费", "supply": "补给", "morale": "士气",
        "training": "训练", "equipment": "装备", "arrears": "欠饷",
        "mobility": "机动", "loyalty": "忠诚", "status": "状态", "owner_power": "归属",
    },
    "buildings": {
        "id": "编号", "region_id": "地区", "name": "建筑", "category": "类别",
        "level": "等级", "condition": "完好", "maintenance": "维护费", "risk": "风险",
        "output_metric": "产出去向", "output_amount": "产出量", "status": "状态",
        "origin": "来源",
    },
    "court_roster": {
        "name": "姓名", "office": "官职", "office_type": "官职类", "faction": "派系",
        "status": "状态", "power_id": "势力", "location": "所在",
    },
    "issue_assignees": {
        "name": "姓名", "office": "官职", "office_type": "官职类", "status": "状态",
        "ability": "能力", "loyalty": "忠诚", "integrity": "清廉", "courage": "胆略",
        "diplomacy": "外交", "martial": "军事", "stewardship": "管理",
        "intrigue": "谋略", "learning": "学识", "faction": "派系",
        "personal_skills": "特长", "style": "风格",
    },
    "departments": {
        "id": "编号", "key": "键", "name": "衙门", "authority_scope": "权责",
        "power": "权力", "effect_summary": "效果", "status": "状态", "origin": "来源",
    },
    "technologies": {
        "id": "编号", "key": "键", "name": "科技", "category": "类别",
        "effect_summary": "效果", "status": "状态", "origin": "来源",
    },
}


def _table_to_tsv(name: str, table: Dict[str, object]) -> str:
    """{cols,rows} → 真 TSV 文本块（tab 分隔、换行分行）。

    放在 json.dumps 之外，避免 \\t/\\n 被 JSON 转义吃掉压缩收益（实测比 dict-of-rows -25%、
    比转义后塞进 JSON 再 -10%）。空表只吐表头行（空）。None → 空串。
    """
    raw_cols = [str(c) for c in (table.get("cols") or [])]
    labels = _TSV_COL_LABELS.get(name, {})
    cols = [labels.get(c, c) for c in raw_cols]
    rows = table.get("rows") or []
    lines = ["\t".join(cols)]
    for r in rows:  # type: ignore[assignment]
        lines.append("\t".join("" if v is None else str(v) for v in r))
    return f"## {name}（TSV，首行列名，tab 分隔）\n" + "\n".join(lines)


def build_simulator_context(simulator_payload: Optional[Dict[str, object]]) -> str:
    """拼 simulator/extractor 共用的盘面前缀段（turn_header + 盘面 TSV 块 + 其余 JSON）。

    缓存关键：simulator 与 extractor 的 system instructions 前缀都是
    `[game_world, simulator_context, ...]`。本函数对二者吐出**字节级一致**的 simulator_context，
    simulator 先跑就把 `game_world + simulator_context` 写进 DeepSeek 前缀缓存，extractor
    再命中。turn_header 文案、取值路径(统一从 payload['turn'])、序列化参数三者两边同源。

    BUG 修复：历史上 simulator 用 state 路径+文案「邸报抬头与正文涉及年月」，extractor 用
    payload['turn']+文案「抽取涉及年月」→ 第一个字节就分叉 → extractor 整段 payload 全 miss。
    实测统一后结算 token -14.7%。

    TSV 优化：`{cols,rows}` 二维表（regions/armies/buildings/court_roster/powers_brief）转**真
    TSV 文本块**（json.dumps 之外，免转义），按「变化最小→最易变」排序——建筑/人物在前，军队/
    地区其次，诏书/记忆/issue 等高频变化字段连同非表字段走尾部 JSON。其余字段（含 factions_brief/
    classes_brief 叙述串、issues/memories 等）维持 JSON。实测表类 -25% token。
    """
    payload = simulator_payload or {}
    turn_header = ""
    if isinstance(payload.get("turn"), dict):
        t = payload["turn"]
        _y, _p = t.get("year"), t.get("period")
        turn_header = (
            f"【本回合年月】{_y} 年 {_p} 月（第 {t.get('turn')} 回合）。"
            f"涉及年月时以此为准。\n"
            f"【奏章第二行必须逐字写】{_y}年{_p}月 {TURN_UNIT}末奏章\n"
            f"不得改成“崇祯元年/正月/第一月”等：纪年用上面的 {_y} 年原数，月份用上面的 {_p} 月原数，"
            f"绝不可拿史实年号或回合序号覆盖这两个数字。\n"
        )

    # 盘面表（{cols,rows}）转 TSV，按「稳→变」排序置前；缺失/非表的跳过。
    table_order = ("buildings", "departments", "technologies", "court_roster", "armies", "regions")
    tsv_blocks: List[str] = []
    consumed: set[str] = set()
    for name in table_order:
        v = payload.get(name)
        if _is_cols_rows_table(v):
            tsv_blocks.append(_table_to_tsv(name, v))  # type: ignore[arg-type]
            consumed.add(name)
    # table_order 未列到、但仍是 {cols,rows} 的表也转 TSV（防新增表字段漏压缩），稳定排序。
    for name in sorted(k for k in payload if k not in consumed and _is_cols_rows_table(payload.get(k))):
        tsv_blocks.append(_table_to_tsv(name, payload[name]))  # type: ignore[arg-type]
        consumed.add(name)

    # Prefix-cache hygiene: keep volatile fields at the tail. Court chat builds a
    # no-decree payload during summoning, while settlement builds a with-decree
    # payload after fiscal tick / auto issues / due secret orders. If fields like
    # decree_text or current_state appear early in this JSON block, DeepSeek can
    # only reuse the table prefix and misses later stable board context. Preserve
    # all data, but serialize low-churn metadata first and high-churn material last.
    stable_rest_order = (
        "preset_catalog",
    )
    volatile_rest_order = (
        "current_state",
        "treasury_brief",
        "factions_brief",
        "classes_brief",
        "powers_brief",
        "active_issues",
        "candidate_events",
        "decree_text",
        "structured_directives",
        "deaths_this_turn",
        "debuts_this_turn",
        "relevant_memories",
        "secret_orders",
        "hitl_min_decisions",
        "data_note",
    )
    rest_source = {k: v for k, v in payload.items() if k not in consumed}
    stable_keys = {k for k in stable_rest_order if k in rest_source}
    volatile_keys = {k for k in volatile_rest_order if k in rest_source}
    rest: Dict[str, object] = {}
    for key in stable_rest_order:
        if key in rest_source:
            rest[key] = rest_source[key]
    for key in rest_source:
        if key not in stable_keys and key not in volatile_keys:
            rest[key] = rest_source[key]
    for key in volatile_rest_order:
        if key in rest_source:
            rest[key] = rest_source[key]
    parts = [turn_header + "【本回合推演输入 simulator_payload】"]
    parts.extend(tsv_blocks)
    parts.append("## 其余字段（JSON）\n" + json.dumps(rest, ensure_ascii=False, sort_keys=False))
    return "\n".join(parts)


def create_season_simulator_agent(
    llm_config: LLMConfig,
    agno_db: SqliteDb,
    state: Optional[GameState] = None,
    db: Optional[object] = None,
    simulator_payload: Optional[Dict[str, object]] = None,
) -> Agent:
    """月末推演日讲官。全量盘面走 user payload，无 tool。
    走 advanced 角色派生：若 advanced_model 已配，用更强模型；否则 fallback 主 model。
    一次性 agent：不传 db，免得 runs 累积撑爆 <db>.emperor.db。"""
    del db, state, agno_db
    cfg = _llm_for_role(llm_config, "simulator")
    tlog(f"[simulator] 使用模型 {cfg.model}")
    temperature, top_p = agent_sampling_settings("simulator")
    # simulator_context 与 extractor 共用 build_simulator_context → 字节一致 → 暖好 extractor 前缀缓存。
    simulator_context = build_simulator_context(simulator_payload)
    season_prompt = _render_hitl_prompt(_ctx().season_simulator_prompt, simulator_payload)
    instructions = [_ctx().game_world_prompt, simulator_context, season_prompt]
    if is_minimax_base_url(cfg.base_url):
        instructions.insert(0, _MINIMAX_SHORT_THINKING_PROMPT)

    return Agent(
        name="月末推演日讲官",
        id="season-simulator",
        model=create_chat_model(cfg, temperature=temperature, top_p=top_p, max_tokens=cfg.max_tokens, enable_thinking=True),
        instructions=instructions,
        add_history_to_context=False,
        markdown=False,
    )


def create_score_extractor_module_agent(
    llm_config: LLMConfig,
    agno_db: SqliteDb,
    module: str,
    simulator_payload: Optional[Dict[str, object]] = None,
    supplemental_context: Optional[Dict[str, object]] = None,
) -> Agent:
    """模块化打分提取员。module 对应 GameContent.score_extractor_module_prompts。"""
    del agno_db  # 一次性 agent，不持久化，免撑爆 .emperor.db
    ctx = _ctx()
    prompt = ctx.score_extractor_module_prompts.get(module)
    if not prompt:
        raise RuntimeError(f"未知结算提取模块：{module}")
    cfg = _llm_for_role(llm_config, "extractor")
    tlog(f"[extractor/{module}] 使用模型 {cfg.model}")
    temperature, top_p = agent_sampling_settings("extractor")
    # 与 simulator 共用同一函数 → simulator_context 字节级一致 → 命中 simulator 暖好的前缀缓存。
    simulator_context = build_simulator_context(simulator_payload)
    supplemental = (
        "【结算补充上下文 extractor_context】\n"
        + json.dumps(supplemental_context or {}, ensure_ascii=False, sort_keys=False)
    )
    return Agent(
        name=f"档房书办-{module}",
        id=f"score-extractor-{module}",
        model=create_chat_model(
            cfg,
            temperature=temperature,
            top_p=top_p,
            max_tokens=cfg.max_tokens,
            enable_thinking=False,
            force_json_output=True,
        ),
        instructions=[ctx.game_world_prompt, simulator_context, ctx.score_extractor_shared_prompt, supplemental, prompt],
        add_history_to_context=False,
        markdown=False,
    )


JSON_SANITIZER_PROMPT = (
    "你是 JSON 修复匠。下面给你一段被污染的 JSON（可能混了思考过程、```json fence、注释、尾随逗号、"
    "重复字段、Markdown 标题等），请只输出**修复后的合法 JSON 字符串**，不要加任何解释、前后缀或 fence。\n"
    "保持原数据结构与字段不变，只做语法清理。若彻底无法识别为 JSON，请尝试抽取里面最像 JSON 的那一段。\n"
    "请按照 json 格式输出。"
)


def create_json_sanitizer_agent(llm_config: LLMConfig, agno_db: SqliteDb) -> Agent:
    """非思考 + response_format=json_object 的 fallback 整理器。一次性，不持久化。"""
    del agno_db
    return Agent(
        name="JSON 修复匠",
        id="json-sanitizer",
        model=create_chat_model(
            llm_config,
            temperature=0.0,
            top_p=0.7,
            max_tokens=max(4000, llm_config.max_tokens),
            enable_thinking=False,
            force_json_output=True,
        ),
        instructions=[JSON_SANITIZER_PROMPT],
        add_history_to_context=False,
        markdown=False,
    )


def create_chapter_memory_agent(llm_config: LLMConfig, agno_db: SqliteDb) -> Agent:
    """章节记忆：把本回合诏书+邸报+落库效果浓缩成 {body, tags} JSON（body 叙事，tags 召回标签）。
    一次性，不持久化。"""
    del agno_db
    ctx = _ctx()
    return Agent(
        name="起居注史官",
        id="chapter-memory",
        model=create_chat_model(
            llm_config,
            temperature=0.1,
            top_p=0.1,
            max_tokens=max(1200, llm_config.max_tokens),
            enable_thinking=False,
            force_json_output=True,
        ),
        instructions=[ctx.game_world_prompt, ctx.chapter_memory_prompt],
        add_history_to_context=False,
        markdown=False,
    )


def create_minister_recap_agent(llm_config: LLMConfig, agno_db: SqliteDb) -> Agent:
    """大臣私人对话纪要：把某大臣本回合与皇帝的奏对（含已办成的拟旨/任命/密令动作）浓缩成
    {recap} JSON，供其下回合召见时回忆「已替皇帝办了什么」，避免空转重复拟旨。一次性，不持久化。"""
    del agno_db
    ctx = _ctx()
    return Agent(
        name="起居注史官",
        id="minister-recap",
        model=create_chat_model(
            llm_config,
            temperature=0.1,
            top_p=0.1,
            max_tokens=max(800, llm_config.max_tokens),
            enable_thinking=False,
            force_json_output=True,
        ),
        instructions=[ctx.game_world_prompt, ctx.minister_recap_prompt],
        add_history_to_context=False,
        markdown=False,
    )


def create_ending_summary_agent(llm_config: LLMConfig, agno_db: SqliteDb) -> Agent:
    """国史编纂官：读全程章节记忆 + 结局类型，生成史评式结局总结（纯文本流式）。一次性，不持久化。"""
    del agno_db
    ctx = _ctx()
    return Agent(
        name="国史编纂官",
        id="ending-summary",
        model=create_chat_model(
            llm_config,
            temperature=0.4,
            top_p=0.5,
            max_tokens=max(2400, llm_config.max_tokens),
            enable_thinking=True,
        ),
        instructions=[ctx.game_world_prompt, ctx.ending_summary_prompt],
        add_history_to_context=False,
        markdown=False,
    )


# --- 自定义剧本生成 ---

_SCENARIO_GEN_PROMPT_ATTR = {
    "characters": "scenario_gen_characters_prompt",
    "events": "scenario_gen_events_prompt",
    "seed_events": "scenario_gen_seed_events_prompt",
}


def create_scenario_generator_agent(llm_config: LLMConfig, agno_db: SqliteDb, target: str) -> Agent:
    """剧本生成员：按玩家构思生成某一个设定文件（characters/events/seed_events）的内容。
    target 决定用哪份生成提示词。走 advanced 角色（长结构化生成）。一次性，不持久化。"""
    del agno_db
    attr = _SCENARIO_GEN_PROMPT_ATTR.get(target)
    if not attr:
        raise RuntimeError(f"未知剧本生成目标：{target}")
    ctx = _ctx()
    prompt = getattr(ctx, attr)
    cfg = _llm_for_role(llm_config, "simulator")
    tlog(f"[scenario-gen/{target}] 使用模型 {cfg.model}")
    return Agent(
        name=f"剧本生成员-{target}",
        id=f"scenario-generator-{target}",
        model=create_chat_model(
            cfg,
            temperature=0.4,
            top_p=0.6,
            max_tokens=max(8000, cfg.max_tokens),
            enable_thinking=False,
            force_json_output=True,
        ),
        instructions=[ctx.game_world_prompt, prompt],
        add_history_to_context=False,
        markdown=False,
    )


def generate_scenario_file(
    llm_config: LLMConfig,
    agno_db: SqliteDb,
    target: str,
    user_prompt: str,
) -> object:
    """生成一个设定文件的内容并返回其 JSON（characters → dict，events/seed_events → list）。

    复用结算同款 parse + sanitizer 兜底；agent 按提示词包一层 {"file": <内容>} 满足
    parse_agent_json 顶层须 object（事件是数组），此处拆封返回内层内容。
    解析彻底失败抛 LLMContractError，由调用方决定降级（标该文件 failed）。"""
    agent = create_scenario_generator_agent(llm_config, agno_db, target)
    raw = run_agent_text(agent, user_prompt, tag=f"scenario-gen/{target}")
    try:
        parsed = parse_agent_json(raw, f"剧本生成-{target}")
    except Exception as parse_err:
        tlog(f"[scenario-gen/{target}] 主输出解析失败：{parse_err}；调 sanitizer 重整")
        sanitizer = create_json_sanitizer_agent(llm_config, agno_db)
        cleaned = run_agent_text(sanitizer, raw, tag=f"scenario-gen/{target}/sanitize")
        parsed = parse_agent_json(cleaned, f"剧本生成-{target}（sanitizer）")
    if not isinstance(parsed, dict) or "file" not in parsed:
        raise LLMContractError(f"剧本生成-{target}：输出缺顶层 file 键。")
    return parsed["file"]


def create_scenario_editor_agent(
    llm_config: LLMConfig,
    agno_db: SqliteDb,
    scenario_id: str,
    tools: list,
) -> Agent:
    """剧本编辑助手：多轮对话 + tool-calling 增删改剧本。走 advanced 角色。
    带持久 agno 历史（session_id 按剧本隔离），跨请求/重启续上下文。非 JSON-only。"""
    ctx = _ctx()
    cfg = _llm_for_role(llm_config, "simulator")
    tlog(f"[scenario-editor/{scenario_id}] 使用模型 {cfg.model}")
    return Agent(
        name="剧本编辑助手",
        id="scenario-editor",
        session_id=f"scenario-editor-{scenario_id}",
        db=agno_db,
        model=create_chat_model(
            cfg,
            temperature=0.3,
            top_p=0.5,
            max_tokens=max(4000, cfg.max_tokens),
            enable_thinking=False,
        ),
        instructions=[ctx.game_world_prompt, ctx.scenario_editor_prompt],
        tools=tools,
        add_history_to_context=True,
        num_history_runs=8,
        tool_call_limit=12,
        markdown=False,
    )
