"""Token 用量统计：monkey-patch openai client 抓取每次 completion 的 usage。L1。

TOKEN_STATS 是进程级遥测，留模块级单例。
_TOKEN_PATCH_INSTALLED 守卫保证补丁只打一次。
"""

import sys
import threading
from datetime import datetime
from typing import Dict

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ming_sim.llm_config import is_dashscope_base_url

TOKEN_STATS: Dict[str, Dict[str, int]] = {}
_token_lock = threading.Lock()
_TOKEN_PATCH_INSTALLED = False

# 非流式 agent（extractor/sanitizer/decree-writer）跑完会从 agno RunMetrics 自记 token（含
# cache_read/write，dashscope 原生 usage 不报这俩）。置位时让 monkeypatch 跳过原生 _record_usage，
# 避免同一次调用被 agno metrics + 原生 usage 双重记账。thread-local：并行 extractor 各线程独立。
_prefer_agno_metrics = threading.local()


def prefer_agno_metrics_enabled() -> bool:
    return getattr(_prefer_agno_metrics, "on", False)


class use_agno_metrics:
    """with 块内：本线程的 openai .create 不走原生 usage 记账，改由调用方用 agno metrics 记。"""
    def __enter__(self):
        self._prev = getattr(_prefer_agno_metrics, "on", False)
        _prefer_agno_metrics.on = True
        return self
    def __exit__(self, *exc):
        _prefer_agno_metrics.on = self._prev
        return False


def ts() -> str:
    now = datetime.now()
    return now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def tlog(msg: str) -> None:
    try:
        print(f"[{ts()}] {msg}", flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        safe = msg.encode(enc, errors="replace").decode(enc, errors="replace")
        print(f"[{ts()}] {safe}", flush=True)


def _guess_caller_tag(kwargs: Dict[str, object]) -> str:
    """从 messages 的所有 system 段拼合后猜哪个 agent 在调用,用于 token 日志可读。"""
    messages = kwargs.get("messages") or []
    sys_text = ""
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "system":
            continue
        c = msg.get("content")
        if isinstance(c, str):
            sys_text += c
        elif isinstance(c, list):
            for item in c:
                if isinstance(item, dict):
                    sys_text += str(item.get("text", ""))
    # minister 必须先判：大臣 system 末尾注入上月邸报全文(simulator 产出，含『日讲官』
    # 『档房书办』等词)，若先判 extractor/simulator 会把大臣对话误标成结算 agent。
    # 大臣自身开场白『扮演被皇帝召见』只在大臣 prompt 出现，且在邸报之前 → 用它先认。
    if "扮演被皇帝召见" in sys_text or "大臣扮演" in sys_text:
        return "minister"
    # 结算/写诏 agent 的 system = game_world_prompt(很长) + 自身 prompt，关键锚点在中后段，
    # 不能只看开头窗口。这几个 agent 不注入邸报，故全文搜各自唯一开场白即可。
    if "档房书办" in sys_text:
        return "extractor"
    if "日讲官兼推演官" in sys_text or "月末推演" in sys_text:
        return "simulator"
    if "诏书润色" in sys_text or "正式诏书" in sys_text:
        return "decree-writer"
    return "?"


def _record_usage(model_id: str, usage: object, caller_tag: str = "?") -> None:
    if usage is None:
        return
    with _token_lock:
        bucket = TOKEN_STATS.setdefault(
            model_id,
            {"calls": 0, "prompt": 0, "completion": 0, "cached": 0, "reasoning": 0, "total": 0},
        )
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", prompt + completion) or 0)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(prompt_details, "cached_tokens", 0) or 0) if prompt_details else 0
        cache_creation = int(getattr(prompt_details, "cache_creation_input_tokens", 0) or 0) if prompt_details else 0
        completion_details = getattr(usage, "completion_tokens_details", None)
        reasoning = int(getattr(completion_details, "reasoning_tokens", 0) or 0) if completion_details else 0
        bucket["calls"] += 1
        bucket["prompt"] += prompt
        bucket["completion"] += completion
        bucket["cached"] += cached
        bucket["cache_creation"] = bucket.get("cache_creation", 0) + cache_creation
        bucket["reasoning"] += reasoning
        bucket["total"] += total
    cc_part = f" cache_creation={cache_creation}" if cache_creation else ""
    print(
        f"[TOKEN] caller={caller_tag} model={model_id} prompt={prompt} cached={cached}{cc_part} "
        f"completion={completion} reasoning={reasoning} total={total}",
        flush=True,
    )


def record_stream_metrics(model_id: str, metrics: object, caller_tag: str = "?") -> None:
    """记录 agno 流式 RunOutput.metrics（RunMetrics）的 token 用量。"""
    if metrics is None:
        return
    prompt = int(getattr(metrics, "input_tokens", 0) or 0)
    completion = int(getattr(metrics, "output_tokens", 0) or 0)
    total = int(getattr(metrics, "total_tokens", prompt + completion) or 0)
    cached = int(getattr(metrics, "cache_read_tokens", 0) or 0)
    cache_creation = int(getattr(metrics, "cache_write_tokens", 0) or 0)
    reasoning = int(getattr(metrics, "reasoning_tokens", 0) or 0)
    if total == 0 and prompt == 0 and completion == 0:
        return
    with _token_lock:
        bucket = TOKEN_STATS.setdefault(
            model_id,
            {"calls": 0, "prompt": 0, "completion": 0, "cached": 0, "reasoning": 0, "total": 0},
        )
        bucket["calls"] += 1
        bucket["prompt"] += prompt
        bucket["completion"] += completion
        bucket["cached"] += cached
        bucket["cache_creation"] = bucket.get("cache_creation", 0) + cache_creation
        bucket["reasoning"] += reasoning
        bucket["total"] += total
    cc_part = f" cache_creation={cache_creation}" if cache_creation else ""
    print(
        f"[TOKEN] caller={caller_tag} model={model_id} prompt={prompt} cached={cached}{cc_part} "
        f"completion={completion} reasoning={reasoning} total={total}",
        flush=True,
    )


def _get_client_base_url(self_client_holder: object) -> str:
    """从 openai Completions self 拿 client.base_url。"""
    try:
        client = getattr(self_client_holder, "_client", None)
        if client is None:
            return ""
        base = getattr(client, "base_url", "")
        return str(base) if base else ""
    except Exception:
        return ""


_DASHSCOPE_STATIC_CACHE_MIN_CHARS = 800

# DashScope 显式缓存会缓存「messages 开头 → cache_control 所在 block 末尾」。
# 这些锚点之后都是月度盘面 / 推演 payload / extractor 补充上下文等高频变化内容，
# 不能放进显式缓存，否则每轮反复 cache_creation、很少命中。
_DASHSCOPE_DYNAMIC_SYSTEM_MARKERS = (
    "【本回合年月】",
    "【本回合推演输入 simulator_payload】",
    "【结算补充上下文 extractor_context】",
    "当前为 ",
    "本回合朝会盘面：",
    "本月朝会盘面：",
    "本旬朝会盘面：",
    "【上回合邸报全文",
    "【上月邸报全文",
    "【近来朝局",
    "【私人对话纪要",
    "【你身上还在办的密令】",
)

def _dashscope_static_prefix_end(content: str) -> int:
    """返回 system 中适合显式缓存的静态前缀长度。"""
    dynamic_starts = []
    for marker in _DASHSCOPE_DYNAMIC_SYSTEM_MARKERS:
        # Match marker only at the beginning of the content or following a newline
        idx = content.find(marker)
        if idx == 0 or (idx > 0 and content[idx - 1] == "\n"):
            dynamic_starts.append(idx)
        else:
            # Check if it appears later in the string following a newline
            idx = content.find("\n" + marker)
            if idx >= 0:
                dynamic_starts.append(idx + 1)
                
    return min(dynamic_starts) if dynamic_starts else len(content)


def _text_block(text: str, cache: bool = False) -> Dict[str, object]:
    block: Dict[str, object] = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def _inject_dashscope_cache_mark(kwargs: Dict[str, object]) -> None:
    """对 DashScope 请求只标静态 system 前缀。

    cache_control 不能落在月度盘面/历史/密令/推演 payload 后面；那些内容每轮会变，
    标进去会导致反复创建主动缓存而不命中。
    """
    messages = kwargs.get("messages")
    if not isinstance(messages, list):
        return
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "system":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            static_end = _dashscope_static_prefix_end(content)
            static_text = content[:static_end]
            if len(static_text) >= _DASHSCOPE_STATIC_CACHE_MIN_CHARS:
                blocks = [_text_block(static_text, cache=True)]
                dynamic_text = content[static_end:]
                if dynamic_text:
                    blocks.append(_text_block(dynamic_text))
                msg["content"] = blocks
        elif isinstance(content, list) and content:
            # 兼容上游已拆 block 的情况：重组文本后按同一规则切分，避免给最后一块
            # （通常是动态上下文）打 cache_control。
            text = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type", "text") == "text"
            )
            if not text:
                break
            static_end = _dashscope_static_prefix_end(text)
            static_text = text[:static_end]
            if len(static_text) >= _DASHSCOPE_STATIC_CACHE_MIN_CHARS:
                blocks = [_text_block(static_text, cache=True)]
                dynamic_text = text[static_end:]
                if dynamic_text:
                    blocks.append(_text_block(dynamic_text))
                msg["content"] = blocks
        break  # 只标第一条 system,够前缀缓存命中


def install_token_stats_patch() -> None:
    """Monkey-patch openai client to capture usage on every chat completion.
    同时对 dashscope 请求注入 cache_control 显式缓存标记。
    """
    global _TOKEN_PATCH_INSTALLED
    if _TOKEN_PATCH_INSTALLED:
        return
    try:
        from openai.resources.chat.completions import Completions, AsyncCompletions  # type: ignore
    except Exception:
        return
    orig_create = Completions.create
    orig_acreate = AsyncCompletions.create

    def patched_create(self, *args, **kwargs):
        base_url = _get_client_base_url(self)
        caller_tag = _guess_caller_tag(kwargs)
        if is_dashscope_base_url(base_url):
            _inject_dashscope_cache_mark(kwargs)
        resp = orig_create(self, *args, **kwargs)
        try:
            if not prefer_agno_metrics_enabled():  # 调用方将用 agno metrics 记账，跳过避免双计
                model_id = getattr(resp, "model", kwargs.get("model", "unknown"))
                _record_usage(model_id, getattr(resp, "usage", None), caller_tag)
        except Exception:
            pass
        return resp

    async def patched_acreate(self, *args, **kwargs):
        base_url = _get_client_base_url(self)
        caller_tag = _guess_caller_tag(kwargs)
        if is_dashscope_base_url(base_url):
            _inject_dashscope_cache_mark(kwargs)
        resp = await orig_acreate(self, *args, **kwargs)
        try:
            if not prefer_agno_metrics_enabled():
                model_id = getattr(resp, "model", kwargs.get("model", "unknown"))
                _record_usage(model_id, getattr(resp, "usage", None), caller_tag)
        except Exception:
            pass
        return resp

    Completions.create = patched_create  # type: ignore
    AsyncCompletions.create = patched_acreate  # type: ignore
    _TOKEN_PATCH_INSTALLED = True


def print_token_summary() -> None:
    if not TOKEN_STATS:
        print("[TOKEN-SUMMARY] no LLM calls captured")
        return
    print("\n========== TOKEN USAGE SUMMARY ==========")
    grand: Dict[str, int] = {}
    for model_id, bucket in TOKEN_STATS.items():
        hit_rate = (bucket["cached"] / bucket["prompt"] * 100) if bucket["prompt"] else 0
        cc = bucket.get("cache_creation", 0)
        cc_part = f" cache_creation={cc}" if cc else ""
        print(
            f"  {model_id}: calls={bucket['calls']} prompt={bucket['prompt']} "
            f"cached={bucket['cached']} ({hit_rate:.1f}%){cc_part} completion={bucket['completion']} "
            f"reasoning={bucket['reasoning']} total={bucket['total']}"
        )
        for key, value in bucket.items():
            grand[key] = grand.get(key, 0) + int(value)
    grand_hit = (grand.get("cached", 0) / grand.get("prompt", 0) * 100) if grand.get("prompt") else 0
    grand_cc = grand.get("cache_creation", 0)
    grand_cc_part = f" cache_creation={grand_cc}" if grand_cc else ""
    print(
        f"  TOTAL: calls={grand.get('calls',0)} prompt={grand.get('prompt',0)} "
        f"cached={grand.get('cached',0)} ({grand_hit:.1f}%){grand_cc_part} completion={grand.get('completion',0)} "
        f"reasoning={grand.get('reasoning',0)} total={grand.get('total',0)}"
    )
    print("=========================================")
