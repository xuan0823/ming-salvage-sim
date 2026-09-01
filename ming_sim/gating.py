"""通用触发条件 DSL 求值器。L4 模块。

一套纯代码求值的触发条件表达式,被多处复用：
  - seed_events.trigger_gate（情势进候选 / auto_trigger 硬立项）
  - events.require（历史锚定 node 的可证伪前提：过则触发，不过则跳过）
  - opening_legacies.clear_gate（开局负面修正的消除判定）

设计要点：
  - **纯代码,过条件即真**。不依赖 LLM 判断（实测 LLM 判前提不可靠）。
  - **and/or 任意嵌套** + 叶子条件。叶子可读 metrics / region / army / building /
    power / class / faction / character / event 表。
  - **向后兼容扁平 dict**：旧的 {key: cond} 视为隐式 AND。

表达式形态（三种节点,递归）：
  - {"and": [<node>, ...]}            全部成立
  - {"or":  [<node>, ...]}            任一成立
  - 叶子,两种等价写法：
      {"key": "char.袁崇焕.in_region", "op": "==", "val": "liaodong"}
      {"key": "国库", "cond": "<=240"}        # cond = 现有比较串语法
  - 扁平 dict（不含保留键 and/or/key）：{"国库": "<=240", "民心": ">=30"} = 隐式 AND
  - 空 dict / None → 恒真（无条件）。

叶子 key 形式（数值走 eval_gate_key,文本走 eval_gate_key_str）：
  - 'metric_name'                              → metrics
  - 'region/army/building.<id>.<field>'        → 对应表数值/文本
  - 'power.<id>.<field>' / 'faction.<name>.<field>'
  - 'class.<name>[@<region>].<field>'          → classes 表（省级/全国/多省聚合）
  - 多目标聚合：'region.a|b|c.<field>.<agg>'    → agg ∈ max/min/avg/sum（多 id 无 agg 默认 min）
  - 'char.<name>.in_region|office_contains|status|power'  → characters 表（文本）
  - 'event.<id>.triggered'                     → event_triggers/issues 是否已触发（"true"/"false"）

任一叶子取值失败/数据缺失 → 该叶子判 False（保守：缺数据即不过）。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict, List, Optional, Union

if TYPE_CHECKING:  # 避免运行时 import GameDB（L3）造成反向依赖；只用作类型注解。
    from ming_sim.db import GameDB

# 触发条件表达式：旧扁平 dict 或 新布尔树。
GateExpr = Union[Dict[str, str], Dict[str, object]]

_GATE_AGG_FUNCS = {
    "max": max,
    "min": min,
    "sum": sum,
    "avg": lambda xs: sum(xs) // max(1, len(xs)),
}

# 叶子结构化写法允许的算子。
_LEAF_OPS = (">=", "<=", ">", "<", "==", "!=", "contains")


def eval_gate_key(key: str, metrics: Dict[str, int], db: "GameDB") -> Optional[int]:
    """把 gate key 解析成一个 int 值。形式见模块 docstring。
    解析失败/数据缺失返回 None（调用方据此判该叶子不通过）。
    """
    if "." not in key:
        if key in metrics:
            return int(metrics[key])
        return None
    parts = key.split(".")
    table = parts[0]
    if table not in ("region", "army", "building", "power", "class", "faction"):
        return None
    # 末段可能是 agg，先抽出
    agg = None
    if parts[-1] in _GATE_AGG_FUNCS:
        agg = parts[-1]
        parts = parts[:-1]
    if len(parts) < 3:
        return None
    field = parts[-1]
    id_segment = ".".join(parts[1:-1])
    if table == "class" and "@" in id_segment and "|" in id_segment.split("@", 1)[1]:
        # 简写：class.<name>@<r1>|<r2>|<r3>.<field> → 展开成 [name@r1, name@r2, name@r3]
        cname, rest = id_segment.split("@", 1)
        ids = [f"{cname}@{r}" for r in rest.split("|") if r]
    else:
        ids = id_segment.split("|") if "|" in id_segment else [id_segment]
        ids = [x for x in ids if x]
    if not ids:
        return None
    # class 表的 id 是 name 或 name@region；其它表 id 就是行 id
    values: List[int] = []
    for cid in ids:
        row = None
        if table == "region":
            if field in ("grain_output", "grain_stock"):
                row = db.conn.execute(
                    f"SELECT json_extract(fiscal,'$.{field}') FROM regions WHERE id = ?",
                    (cid,),
                ).fetchone()
            else:
                row = db.conn.execute(f"SELECT {field} FROM regions WHERE id = ?", (cid,)).fetchone()
        elif table == "army":
            row = db.conn.execute(f"SELECT {field} FROM armies WHERE id = ?", (cid,)).fetchone()
        elif table == "building":
            row = db.conn.execute(f"SELECT {field} FROM buildings WHERE id = ?", (cid,)).fetchone()
        elif table == "power":
            row = db.conn.execute(f"SELECT {field} FROM powers WHERE id = ?", (cid,)).fetchone()
        elif table == "faction":
            # factions 表主键是 name（中文，如 阉党），field 取 leverage/satisfaction
            row = db.conn.execute(f"SELECT {field} FROM factions WHERE name = ?", (cid,)).fetchone()
        elif table == "class":
            if "@" in cid:
                cname, rid = cid.split("@", 1)
            else:
                cname, rid = cid, ""
            row = db.conn.execute(
                f"SELECT {field} FROM classes WHERE name = ? AND region_id = ?",
                (cname, rid),
            ).fetchone()
        if row is None:
            return None
        try:
            values.append(int(row[0]))
        except (TypeError, ValueError):
            return None
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    if agg is None:
        # 多 id 但没指明聚合 → 默认 min（最严苛，要全部满足）
        agg = "min"
    return _GATE_AGG_FUNCS[agg](values)


def eval_gate_key_str(key: str, db: "GameDB") -> Optional[str]:
    """取一个文本型字段值（如 region.<id>.controlled_by → 'ming'/'houjin'）。
    支持单 id 的 region/army/power 文本字段，以及 character / event 叶子。
    解析失败/数据缺失返回 None。
    """
    parts = key.split(".")
    if len(parts) != 3:
        return None
    table, cid, field = parts

    # character 叶子：char.<name>.<field>（人名无点，cid 即 name）
    if table == "char":
        row = db.conn.execute(
            "SELECT location, office, status, power_id FROM characters WHERE name = ?",
            (cid,),
        ).fetchone()
        if row is None:
            return None  # 人物不存在 → 该叶子判 False
        loc, office, status, power = row[0], row[1], row[2], row[3]
        if field == "in_region":
            s = str(loc).strip()
            return s if s else None  # location 为空 → None → 不过（"没地点就当不存在"）
        if field == "office_contains":
            return str(office)  # 子串包含由 op==contains 在 _eval_leaf 处理
        if field == "status":
            return str(status)
        if field == "power":
            return str(power)
        return None

    # event 叶子：event.<id>.triggered → "true"/"false"
    if table == "event":
        if field != "triggered":
            return None
        return "true" if _event_triggered(cid, db) else "false"

    sql = {
        "region": f"SELECT {field} FROM regions WHERE id = ?",
        "army": f"SELECT {field} FROM armies WHERE id = ?",
        "power": f"SELECT {field} FROM powers WHERE id = ?",
    }.get(table)
    if sql is None:
        return None
    row = db.conn.execute(sql, (cid,)).fetchone()
    if row is None:
        return None
    return str(row[0])


def _event_triggered(event_id: str, db: "GameDB") -> bool:
    """某历史事件是否已触发过（与 issues._spawned_event_refs 同源）。
    既看 event_triggers 表，也看由其立项的 issue（origin_kind='event_pool'）。"""
    row = db.conn.execute(
        "SELECT 1 FROM event_triggers WHERE event_id = ? LIMIT 1", (event_id,)
    ).fetchone()
    if row is not None:
        return True
    row = db.conn.execute(
        "SELECT 1 FROM issues WHERE origin_kind='event_pool' AND origin_ref = ? LIMIT 1",
        (event_id,),
    ).fetchone()
    return row is not None


def _eval_cond_str(key: str, cond: str, metrics: Dict[str, int], db: "GameDB") -> bool:
    """求值单条「key cond串」。cond 形如 '<=240'（数值）或 '==ming'/'!=ming'（文本相等）。
    取值失败 → False。这是原 _gate_passed 循环体的等价抽取。"""
    cond = str(cond).strip()
    # 文本相等：==<word> / !=<word>（RHS 非纯数字）
    sm = re.match(r"^(==|!=)\s*(.+)$", cond)
    if sm and not re.match(r"^-?\d+$", sm.group(2).strip()):
        sop, sval = sm.group(1), sm.group(2).strip()
        cur = eval_gate_key_str(key, db)
        if cur is None:
            return False
        if sop == "==":
            return cur == sval
        return cur != sval  # !=
    m = re.match(r"^(>=|<=|>|<|==|!=)\s*(-?\d+)$", cond)
    if not m:
        return False
    op, num = m.group(1), int(m.group(2))
    val = eval_gate_key(key, metrics, db)
    if val is None:
        return False
    if op == ">=":
        return val >= num
    if op == "<=":
        return val <= num
    if op == ">":
        return val > num
    if op == "<":
        return val < num
    if op == "!=":
        return val != num
    return val == num  # ==


def _eval_leaf(node: Dict[str, object], metrics: Dict[str, int], db: "GameDB") -> bool:
    """求值结构化叶子。两种写法：
      - {"key":..., "cond": "<=240"}          → 复用 _eval_cond_str
      - {"key":..., "op": ..., "val": ...}     → op ∈ 比较算子 / contains
    取值失败 → False。"""
    key = str(node["key"])
    if "cond" in node:
        return _eval_cond_str(key, str(node["cond"]), metrics, db)
    op = str(node.get("op", ""))
    val = node.get("val")
    if op == "contains":
        cur = eval_gate_key_str(key, db)
        return cur is not None and str(val) in cur
    # val 是数字 → 数值比较；val 是字符串 → 文本 ==/!=
    if isinstance(val, bool):  # 防 bool 被当 int
        val = str(val).lower()
    if isinstance(val, int):
        return _eval_cond_str(key, f"{op}{val}", metrics, db)
    # 文本：仅 == / !=
    cur = eval_gate_key_str(key, db)
    if cur is None:
        return False
    if op == "==":
        return cur == str(val)
    if op == "!=":
        return cur != str(val)
    return False


def evaluate_gate(expr: Optional[GateExpr], metrics: Dict[str, int], db: "GameDB") -> bool:
    """求值一个触发条件表达式（布尔树 / 扁平 dict / 空）。统一入口。
    空 dict / None → True（无条件恒真，保持现有 gate 语义）。"""
    if not expr:
        return True
    if not isinstance(expr, dict):
        return False
    if "and" in expr:
        return all(evaluate_gate(c, metrics, db) for c in expr["and"])  # type: ignore[union-attr]
    if "or" in expr:
        return any(evaluate_gate(c, metrics, db) for c in expr["or"])  # type: ignore[union-attr]
    if "key" in expr:
        return _eval_leaf(expr, metrics, db)
    # 扁平 dict（key→cond串），隐式 AND
    return all(_eval_cond_str(str(k), str(v), metrics, db) for k, v in expr.items())
