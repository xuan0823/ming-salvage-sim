"""激活剧本指针：解析当前生效的自定义剧本目录。L1。

自定义剧本 = content/ 下三文件（characters.json / events.json / seed_events.json）
的可写覆盖，落在 user_data_dir()/scenarios/<id>/。一次只激活一套，指针存
runtime_scenario.json（仿 runtime_llm.json）。

assets.load_*_asset 读盘前调 active_scenario_dir()：激活剧本里有该文件就用它，
否则回退默认 content/（部分覆盖 + 「取不到才取默认」）。

性能：所有 load_*_asset（一次 GameContent.load 共 32 次）都走这里，故把已解析的
剧本目录缓存进内存，一次 load 只读 1 次盘；默认态（无激活）下直接内存返回 None，
热路径零读盘。set_active_scenario / override 负责失效缓存。

导入无副作用：路径解析全部惰性（用函数而非模块常量），import 本身不读盘、不建目录。
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from ming_sim.paths import user_data_dir, user_data_path

# 进程内临时覆盖槽（校验用，优先于持久指针）。
_OVERRIDE_DIR: Optional[str] = None
_OVERRIDE_SET: bool = False

# 内存缓存的已解析剧本目录。_RESOLVED=True 表示已解析（_RESOLVED_DIR 可能为 None）。
_RESOLVED_DIR: Optional[str] = None
_RESOLVED: bool = False

# 保护上述全局槽（override + 缓存）：剧本校验（override）与 assets 加载（active_scenario_dir）
# 可能来自不同线程（web 端点 + 菜单操作），不加锁会互相踩缓存。
_LOCK = threading.RLock()


def _runtime_scenario_path() -> str:
    return user_data_path("runtime_scenario.json")


def scenarios_root() -> Path:
    """剧本根目录 user_data_dir()/scenarios（按需建）。"""
    root = user_data_dir() / "scenarios"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _invalidate_cache() -> None:
    global _RESOLVED, _RESOLVED_DIR
    _RESOLVED = False
    _RESOLVED_DIR = None


def active_scenario_id() -> str:
    """读 runtime_scenario.json 的 active_id。缺/坏返回 ""（容错，绝不抛）。"""
    path = _runtime_scenario_path()
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("active_id", "") or "").strip()


def active_scenario_dir() -> Optional[str]:
    """当前生效剧本目录，无激活/目录缺失返回 None。

    优先返回进程内 override；否则用内存缓存，未缓存才读盘解析并缓存。
    陈旧指针（指向已删目录）静默回退 None。
    """
    with _LOCK:
        if _OVERRIDE_SET:
            return _OVERRIDE_DIR
        global _RESOLVED, _RESOLVED_DIR
        if _RESOLVED:
            return _RESOLVED_DIR
        scenario_id = active_scenario_id()
        resolved: Optional[str] = None
        if scenario_id:
            candidate = user_data_dir() / "scenarios" / scenario_id
            if candidate.is_dir():
                resolved = str(candidate)
        _RESOLVED_DIR = resolved
        _RESOLVED = True
        return resolved


def set_active_scenario(scenario_id: Optional[str]) -> None:
    """写/清 runtime_scenario.json 并失效缓存。None/空 = 停用（回默认）。"""
    path = _runtime_scenario_path()
    cleaned = (scenario_id or "").strip()
    if not cleaned:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"active_id": cleaned}, fh, ensure_ascii=False)
    with _LOCK:
        _invalidate_cache()


@contextmanager
def override(scenario_dir: Optional[str]) -> Iterator[None]:
    """临时把激活目录指向 scenario_dir（不写盘），供 validate_scenario_dir 用。

    进/出都失效缓存，免得校验时读到旧缓存或污染后续解析。
    """
    with _LOCK:
        global _OVERRIDE_DIR, _OVERRIDE_SET
        prev_dir, prev_set = _OVERRIDE_DIR, _OVERRIDE_SET
        _OVERRIDE_DIR = scenario_dir
        _OVERRIDE_SET = True
        _invalidate_cache()
        try:
            yield
        finally:
            _OVERRIDE_DIR, _OVERRIDE_SET = prev_dir, prev_set
            _invalidate_cache()
