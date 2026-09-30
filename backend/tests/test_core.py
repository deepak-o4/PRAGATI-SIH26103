import unittest
from datetime import date, timedelta
from tests.helpers import *
from app.analytics.metrics import cost_metrics, schedule_metrics, progress_metrics
from app.risk.engine import compute_risk, RiskConfig, risk_history, DEFAULT_WEIGHTS
from app.forecasting.forecast import forecast_completion
from app.scenarios.simulate import run_scenario, ScenarioAdjustments
from app.domain.types import *


class TestCost(unittest.TestCase):
    def test_overrun(self):
        c = cost_metrics(mk())
        self.assertEqual(c.cost_overrun_amount, 200.0)
        self.assertAlmostEqual(c.cost_overrun_pct, 20.0)
        self.assertAlmostEqual(c.expenditure_ratio_pct, 50.0)   # 600/1200
        self.assertAlmostEqual(c.expenditure_vs_progress_pts, 0.0)

    def test_missing_revised_not_fabricated(self):
        c = cost_metrics(mk(revised_cost_crore=None))
        self.assertIsNone(c.cost_overrun_pct); self.assertIsNone(c.cost_overrun_amount)
        self.assertAlmostEqual(c.expenditure_ratio_pct, 60.0)  # falls back to original as basis
        self.assertTrue(any("revised cost missing" in n for n in c.notes))

    def test_zero_original(self):
        c = cost_metrics(mk(original_cost_crore=0.0))
        self.assertIsNone(c.cost_overrun_pct)
        self.assertEqual(c.cost_overrun_amount, 1200.0)

    def test_negative_treated_invalid(self):
        c = cost_metrics(mk(original_cost_crore=-5.0))
        self.assertIsNone(c.cost_overrun_pct)
        self.assertTrue(any("negative" in n for n in c.notes))

    def test_all_missing(self):
        c = cost_metrics(mk(original_cost_crore=None, revised_cost_crore=None, cumulative_expenditure_crore=None))
        self.assertIsNone(c.expenditure_ratio_pct)


class TestSchedule(unittest.TestCase):
    def test_delay_components(self):
        s = schedule_metrics(mk(), AS_OF)
        self.assertEqual(s.revised_slip_days, 365)
        self.assertEqual(s.overdue_days, 0)
        self.assertEqual(s.schedule_delay_days, 365)
        self.assertEqual(s.days_remaining, (date(2027, 1, 1) - AS_OF).days)
        self.assertEqual(s.days_remaining, 93)
        self.assertEqual(s.deadline_proximity, "NEAR")

    def test_overdue_distinguished_from_revised_slip(self):
        s = schedule_metrics(mk(revised_end_date=date(2026, 6, 30)), AS_OF)
        self.assertEqual(s.revised_slip_days, (date(2026, 6, 30) - date(2026, 1, 1)).days)
        self.assertEqual(s.overdue_days, (AS_OF - date(2026, 6, 30)).days)
        self.assertEqual(s.deadline_proximity, "OVERDUE")

    def test_completed_not_overdue(self):
        s = schedule_metrics(mk(status=ProjectStatus.COMPLETED, physical_progress_pct=100.0, revised_end_date=date(2026, 6, 30)), AS_OF)
        self.assertEqual(s.overdue_days, 0)

    def test_missing_dates(self):
        s = schedule_metrics(mk(start_date=None, original_end_date=None, revised_end_date=None), AS_OF)
        self.assertIsNone(s.schedule_delay_days); self.assertIsNone(s.days_remaining)

    def test_invalid_order_flagged(self):
        s = schedule_metrics(mk(start_date=date(2026, 5, 1), original_end_date=date(2026, 1, 1)), AS_OF)
        self.assertIsNone(s.planned_duration_days)
        self.assertTrue(any("precedes" in n for n in s.notes))


class TestProgress(unittest.TestCase):
    def test_velocity_and_change(self):
        p = mk(snapshots=snaps([10, 20, 35]))
        g = progress_metrics(p, AS_OF)
        self.assertEqual(g.progress_change_pts, 15)
        self.assertGreater(g.progress_velocity_pts_per_month, 0)
        self.assertFalse(g.is_stagnant)

    def test_stagnation(self):
        g = progress_metrics(mk(snapshots=snaps([40, 40, 40, 40])), AS_OF)
        self.assertTrue(g.is_stagnant); self.assertEqual(g.stagnant_snapshots, 3)

    def test_single_snapshot_velocity_none(self):
        g = progress_metrics(mk(snapshots=snaps([40])), AS_OF)
        self.assertIsNone(g.progress_velocity_pts_per_month)

    def test_imbalance_flag_is_indicator(self):
        g = progress_metrics(mk(cumulative_expenditure_crore=840.0, physical_progress_pct=40.0, financial_progress_pct=None), AS_OF)
        self.assertAlmostEqual(g.cost_progress_imbalance_pts, 30.0)   # 70% spent vs 40% built
        self.assertTrue(g.imbalance_flag)


class TestRisk(unittest.TestCase):
    def test_default_weights_match_spec(self):
        w = RiskConfig().normalised_weights()
        self.assertEqual({k: round(v) for k, v in w.items() if k != "issues"},
                         {"schedule": 25, "cost": 20, "progress": 25, "milestone": 15, "trend": 10, "data_quality": 5})

    def test_score_is_sum_of_contributors(self):
        p = mk(snapshots=snaps([10, 12, 14, 15]), milestones=(Milestone("a", date(2025, 1, 1), date(2026, 1, 1)),))
        r = compute_risk(p, AS_OF)
        self.assertAlmostEqual(r.score, round(sum(c.points for c in r.contributors), 1), delta=0.3)
        self.assertTrue(all(c.explanation for c in r.contributors))

    def test_bands(self):
        for s, b in [(0, "STABLE"), (30, "STABLE"), (31, "WATCH"), (60, "WATCH"), (61, "WARNING"), (80, "WARNING"), (81, "CRITICAL"), (100, "CRITICAL")]:
            self.assertEqual(risk_band(s).value, b)

    def test_bad_project_worse_than_good(self):
        good = mk(revised_cost_crore=1010.0, revised_end_date=date(2026, 1, 1), original_end_date=date(2026, 12, 31),
                  physical_progress_pct=80.0, snapshots=snaps([60, 70, 80]))
        bad = mk(revised_cost_crore=1600.0, revised_end_date=date(2026, 3, 1), physical_progress_pct=30.0,
                 snapshots=snaps([28, 29, 30, 30, 30]),
                 milestones=(Milestone("m", date(2024, 1, 1), date(2025, 1, 1)),))
        rg, rb = compute_risk(good, AS_OF), compute_risk(bad, AS_OF)
        self.assertLess(rg.score, rb.score)
        self.assertIn(rb.band.value, ("WARNING", "CRITICAL"))

    def test_missing_data_reported_not_scored(self):
        p = mk(revised_cost_crore=None, original_cost_crore=None, snapshots=())
        r = compute_risk(p, AS_OF)
        cost = next(c for c in r.contributors if c.key == "cost")
        self.assertFalse(cost.available); self.assertEqual(cost.points, 0.0)
        self.assertLess(r.assessed_weight_pct, 100)

    def test_terminal_status_not_risky(self):
        self.assertEqual(compute_risk(mk(status=ProjectStatus.COMPLETED), AS_OF).score, 0.0)

    def test_config_env_validation(self):
        import os
        os.environ["RISK_WEIGHTS_JSON"] = '{"bogus": 5}'
        try:
            with self.assertRaises(ValueError): RiskConfig.from_env()
            os.environ["RISK_WEIGHTS_JSON"] = '{"schedule": -1}'
            with self.assertRaises(ValueError): RiskConfig.from_env()
            os.environ["RISK_WEIGHTS_JSON"] = '{"schedule": 50}'
            self.assertEqual(RiskConfig.from_env().weights["schedule"], 50.0)
        finally:
            del os.environ["RISK_WEIGHTS_JSON"]

    def test_history_uses_only_then_available_info(self):
        p = mk(snapshots=snaps([10, 20, 30]), issues=(Issue(IssueType.LAND, Severity.CRITICAL, reported_date=date(2026, 3, 15)),))
        h = risk_history(p)
        self.assertEqual(len(h), 3)
        # issue reported in March must not exist in Jan/Feb views
        from app.risk.engine import project_as_of
        self.assertEqual(len(project_as_of(p, date(2026, 2, 1)).issues), 0)
        self.assertEqual(len(project_as_of(p, date(2026, 3, 1)).issues), 1)


class TestForecast(unittest.TestCase):
    def test_linear(self):
        p = mk(snapshots=snaps([10, 20, 30, 40, 50, 60], date(2026, 1, 1)), physical_progress_pct=60.0)
        f = forecast_completion(p, AS_OF)
        self.assertEqual(f.status, "OK")
        self.assertAlmostEqual(f.velocity_pts_per_month, 10.0, delta=0.6)
        self.assertGreater(f.predicted_completion_date, date(2026, 6, 1))
        self.assertEqual(f.official_revised_end_date, date(2027, 1, 1))   # never overwritten
        self.assertEqual(f.origin, "PREDICTED")

    def test_insufficient_and_stalled_and_complete(self):
        self.assertEqual(forecast_completion(mk(snapshots=snaps([10])), AS_OF).status, "INSUFFICIENT_HISTORY")
        self.assertEqual(forecast_completion(mk(snapshots=snaps([30, 30, 30])), AS_OF).status, "STALLED")
        self.assertEqual(forecast_completion(mk(physical_progress_pct=100.0), AS_OF).status, "COMPLETED")

    def test_low_confidence_for_noisy_short_history(self):
        f = forecast_completion(mk(snapshots=snaps([10, 25, 22, 40])), AS_OF)
        self.assertIn(f.confidence_label, ("LOW", "MEDIUM"))


class TestScenario(unittest.TestCase):
    def setUp(self):
        self.p = mk(snapshots=snaps([10, 15, 20, 25, 30]), physical_progress_pct=30.0,
                    milestones=(Milestone("m", date(2025, 1, 1), date(2026, 3, 1)),),
                    issues=(Issue(IssueType.PROCUREMENT, Severity.CRITICAL),))

    def test_progress_boost_lowers_risk_and_labelled(self):
        r = run_scenario(self.p, ScenarioAdjustments(progress_increase_pts=10), AS_OF)
        self.assertLessEqual(r["delta"]["risk_score"], 0)
        self.assertIn("SIMULATION", r["label"])

    def test_slip_increases_risk(self):
        r = run_scenario(self.p, ScenarioAdjustments(completion_slip_days=60), AS_OF)
        self.assertGreater(r["delta"]["risk_score"], 0)

    def test_issue_resolution_warns_when_weight_zero(self):
        r = run_scenario(self.p, ScenarioAdjustments(resolve_all_critical=True), AS_OF)
        self.assertEqual(r["delta"]["risk_score"], 0)
        self.assertTrue(r["warnings"])

    def test_issue_resolution_moves_risk_when_weighted(self):
        cfg = RiskConfig(weights={**DEFAULT_WEIGHTS, "issues": 10.0})
        r = run_scenario(self.p, ScenarioAdjustments(resolve_all_critical=True), AS_OF, cfg)
        self.assertLess(r["delta"]["risk_score"], 0)

    def test_original_project_not_mutated(self):
        before = self.p.physical_progress_pct
        run_scenario(self.p, ScenarioAdjustments(progress_increase_pts=20), AS_OF)
        self.assertEqual(self.p.physical_progress_pct, before)

    def test_milestone_delay(self):
        r = run_scenario(self.p, ScenarioAdjustments(milestone_delay_days=30), AS_OF)
        self.assertTrue(r["assumptions"])


class TestStatusMachine(unittest.TestCase):
    def test_transitions(self):
        self.assertTrue(can_transition(ProjectStatus.PLANNED, ProjectStatus.UNDER_PREPARATION))
        self.assertFalse(can_transition(ProjectStatus.PLANNED, ProjectStatus.COMPLETED))
        self.assertFalse(can_transition(ProjectStatus.COMPLETED, ProjectStatus.ON_TRACK))
        self.assertTrue(can_transition(ProjectStatus.DELAYED, ProjectStatus.ON_TRACK))

if __name__ == "__main__":
    unittest.main()
