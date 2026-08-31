"""回归测试：针对本轮审查修复的 bug 逐项钉死。

覆盖：H1 外国省份税收过滤 / H2 自动结案效果落账 / H3 惯性漂移结案同口径 /
L3 军报表口径 / M7 军饷足额自动抵旧欠 / L7 军名-地区匹配消歧。
"""

import json
import unittest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.flows import apply_fixed_period_flows, calc_province_fiscal
from ming_sim.matching import match_army_id_from_text, match_region_id_from_text
import ming_sim.issues as issues


class RegressionFixesTests(unittest.TestCase):
    def setUp(self):
        self.content = GameContent.load()
        self.db = GameDB(":memory:", self.content)
        self.db.seed_static_data()
        self.state = self.db.load_state()

    def test_foreign_provinces_excluded_from_treasury(self):
        """H1：外国省份的田赋/辽饷/盐税/商税不得计入大明国库月收。"""
        gk, _nk, details = calc_province_fiscal(self.state, self.db)
        ming_ids = {
            str(r["id"])
            for r in self.db.conn.execute(
                "SELECT id FROM regions WHERE controlled_by = 'ming'"
            ).fetchall()
        }
        detail_ids = {str(d["region_id"]) for d in details}
        self.assertTrue(detail_ids, "ming 省份税收明细不应为空")
        self.assertTrue(
            detail_ids <= ming_ids,
            f"foreign provinces leaked into treasury: {detail_ids - ming_ids}",
        )
        self.assertEqual(gk, sum(d["province_total"] for d in details))

    def test_army_report_matches_ming_only_scope(self):
        """L3：建档兵力合计只算大明军（与维护费口径一致），不再混入敌国军。"""
        report = self.db.army_report(limit=1)
        ming_manpower = int(self.db.conn.execute(
            "SELECT COALESCE(SUM(manpower), 0) FROM armies WHERE active = 1 AND owner_power = 'ming'"
        ).fetchone()[0])
        all_manpower = int(self.db.conn.execute(
            "SELECT COALESCE(SUM(manpower), 0) FROM armies WHERE active = 1"
        ).fetchone()[0])
        self.assertIn(str(ming_manpower), report)
        if all_manpower != ming_manpower:
            self.assertNotIn(str(all_manpower), report)

    def test_auto_assignee_resolve_applies_terminal_effect(self):
        """H2：无承办人自动推进到 bar=100 结案时，effect_on_resolve 必须真落账。"""
        issue_id = self.db.insert_issue(
            self.state,
            kind="situation",
            title="丰年祥瑞",
            bar_value=99,
            inertia=3,
            effect_on_resolve={"metrics": {"民心": 5}},
            effect_on_fail={},
        )
        before = int(self.state.metrics["民心"])
        touched: set = set()
        advances: list = []
        issues._ensure_issue_monthly_motion(
            self.db, self.state, touched, advances, issues._compact_issue_log
        )
        row = self.db.conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        self.assertEqual(row["status"], "resolved")
        # 遗产修正符会按百分比放大民心增量，这里只断言「确实加了分」而非精确值。
        self.assertGreater(int(self.state.metrics["民心"]), before)

    def test_inertia_drift_resolve_applies_fiscal_effect(self):
        """H3：inertia 漂移结案与 extractor 路径同口径（fiscal 也落账）。"""
        issue_id = self.db.insert_issue(
            self.state,
            kind="situation",
            title="加征盐税",
            bar_value=98,
            inertia=2,
            effect_on_resolve={
                "metrics": {"民心": -3},
                "fiscal": [{"tax": "盐税", "ratio": 1.5}],
            },
            effect_on_fail={},
        )
        rows = self.db.conn.execute(
            "SELECT id, fiscal FROM regions WHERE controlled_by = 'ming'"
        ).fetchall()
        before_vals = {
            str(r["id"]): int(json.loads(r["fiscal"] or "{}").get("salt_tax", 0) or 0)
            for r in rows
        }
        base = int(self.state.metrics["民心"])
        issues.apply_issue_inertia_and_ongoing(self.db, self.state, touched_ids=set())
        row = self.db.conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        self.assertEqual(row["status"], "resolved")
        # 遗产修正符会按百分比放大民心增量，这里只断言「确实降了分」而非精确值。
        self.assertLess(int(self.state.metrics["民心"]), base)
        changed = False
        for r in self.db.conn.execute(
            "SELECT id, fiscal FROM regions WHERE controlled_by = 'ming'"
        ).fetchall():
            after = int(json.loads(r["fiscal"] or "{}").get("salt_tax", 0) or 0)
            before = before_vals.get(str(r["id"]), 0)
            if after != before:
                changed = True
        self.assertTrue(changed, "结案 fiscal 效果未落库")

    def test_salary_surplus_pays_old_arrears(self):
        """M7：月饷足额且国库有盈余 → 自动抵扣旧欠（不下穿 0），并记流水。"""
        self.state.metrics["国库"] = 100000.0
        row = self.db.conn.execute(
            "SELECT * FROM armies WHERE owner_power='ming' AND maintenance_per_turn > 0 AND active = 1"
        ).fetchone()
        army_id = row["id"]
        self.db.conn.execute("UPDATE armies SET arrears = 20 WHERE id = ?", (army_id,))
        self.db.conn.commit()
        apply_fixed_period_flows(self.db, self.state)
        after = int(self.db.conn.execute(
            "SELECT arrears FROM armies WHERE id = ?", (army_id,)
        ).fetchone()[0])
        self.assertEqual(after, 0, "足额月饷后旧欠应被自动抵扣")
        n = int(self.db.conn.execute(
            "SELECT COUNT(*) AS n FROM economy_ledger WHERE reason LIKE '%旧欠自动抵扣%'"
        ).fetchone()["n"])
        self.assertGreaterEqual(n, 1, "抵扣应有 economy_ledger 流水")

    def test_matching_army_region_disambiguation(self):
        """L7：'兵部'（共享 controller）不再进军名匹配；'辽东军' 命中军队而非地区。"""
        self.assertIsNone(match_army_id_from_text("兵部", self.content.armies))
        self.assertIsNone(match_army_id_from_text("辽东外线", self.content.armies))
        self.assertEqual(match_army_id_from_text("辽东军", self.content.armies), "guanning")
        self.assertIsNone(match_region_id_from_text("辽东军", self.content.regions))
        self.assertEqual(match_region_id_from_text("辽东", self.content.regions), "liaodong")


if __name__ == "__main__":
    unittest.main()
