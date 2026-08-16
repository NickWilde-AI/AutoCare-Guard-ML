"""Tests for monitoring and drift detection."""

import pytest

from im_guard_ml.monitoring import build_monitoring_report, build_sliding_window_report, compare_reports
from im_guard_ml.drift_detection import (
    chi_square_test,
    ks_test,
    population_stability_index,
    detect_drift,
)


class TestBuildMonitoringReport:
    def test_basic_report(self):
        rows = [
            {
                "prediction": {
                    "risk_level": "high_risk",
                    "final_judgment": "exist_violation",
                    "handling_suggestion": "ban_account",
                },
                "audit_scene": {"behavior_key_summary": {"gift_total_value": 10000}},
                "chat_evidence_list": [{"content": "test"}],
                "behavior_abnormal_list": [{"abnormal_type": "test"}],
            },
            {
                "prediction": {
                    "risk_level": "low_risk",
                    "final_judgment": "not_exist_violation",
                    "handling_suggestion": "ignore",
                },
                "audit_scene": {"behavior_key_summary": {"gift_total_value": 100}},
                "chat_evidence_list": [{"content": "hello"}],
                "behavior_abnormal_list": [],
            },
        ]
        report = build_monitoring_report(rows)
        assert report["total"] == 2
        assert "risk_level" in report["prediction_distribution"]
        assert "ban_account_rate" in report["quality_guards"]
        assert report["quality_guards"]["ban_account_rate"] == 0.5

    def test_empty_input(self):
        report = build_monitoring_report([])
        assert report["total"] == 0


class TestCompareReports:
    def test_no_change(self):
        report = {
            "total": 100,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.5, "mid_risk": 0.3, "high_risk": 0.2},
                "handling_suggestion": {"ignore": 0.5, "warning": 0.3},
            },
            "input_distribution": {
                "gift_total_value": {"mean": 500.0},
            },
        }
        delta = compare_reports(report, report)
        assert delta["total_delta"] == 0
        assert delta["gift_total_value_mean_delta"] == 0.0


class TestSlidingWindowReport:
    def test_detects_abnormal_window(self):
        safe_rows = [
            {
                "prediction": {
                    "risk_level": "low_risk",
                    "final_judgment": "not_exist_violation",
                    "handling_suggestion": "ignore",
                },
                "chat_evidence_list": ["正常聊天"],
                "behavior_abnormal_list": ["normal"],
            }
            for _ in range(10)
        ]
        risky_rows = [
            {
                "prediction": {
                    "risk_level": "high_risk",
                    "final_judgment": "exist_violation",
                    "handling_suggestion": "ban_account",
                },
                "chat_evidence_list": ["违规"],
                "behavior_abnormal_list": ["abnormal"],
            }
            for _ in range(10)
        ]

        report = build_sliding_window_report(
            safe_rows + risky_rows,
            window_size=10,
            step_size=10,
            thresholds={"ban_account_rate_warn": 0.2, "ban_account_rate_critical": 0.5},
        )

        assert report["status"] == "critical"
        assert report["window_count"] == 2
        assert report["windows"][1]["status"] == "critical"

    def test_rejects_invalid_window_size(self):
        with pytest.raises(ValueError, match="window_size"):
            build_sliding_window_report([], window_size=0)


class TestChiSquareTest:
    def test_identical_distributions(self):
        obs = {"a": 50, "b": 30, "c": 20}
        exp = {"a": 50, "b": 30, "c": 20}
        chi2, p = chi_square_test(obs, exp)
        assert chi2 < 1.0
        assert p > 0.5

    def test_very_different_distributions(self):
        obs = {"a": 90, "b": 5, "c": 5}
        exp = {"a": 30, "b": 30, "c": 40}
        chi2, p = chi_square_test(obs, exp)
        assert chi2 > 10.0
        assert p < 0.05

    def test_empty_category(self):
        obs = {"a": 50, "b": 50}
        exp = {"a": 50, "b": 50, "c": 0}
        chi2, p = chi_square_test(obs, exp)
        # Should handle gracefully
        assert chi2 >= 0


class TestKSTest:
    def test_identical_samples(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        d, p = ks_test(a, b)
        assert d < 0.3  # Small D for identical samples
        assert p > 0.1

    def test_very_different_samples(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0] * 10
        b = [50.0, 60.0, 70.0, 80.0, 90.0] * 10
        d, p = ks_test(a, b)
        assert d > 0.8
        assert p < 0.05

    def test_empty_samples(self):
        d, p = ks_test([], [1.0, 2.0])
        assert d == 0.0
        assert p == 1.0


class TestPSI:
    def test_identical_distributions(self):
        dist = {"a": 0.5, "b": 0.3, "c": 0.2}
        psi = population_stability_index(dist, dist)
        assert psi < 0.001

    def test_shifted_distribution(self):
        baseline = {"a": 0.5, "b": 0.3, "c": 0.2}
        current = {"a": 0.2, "b": 0.3, "c": 0.5}
        psi = population_stability_index(baseline, current)
        assert psi > 0.1  # Should indicate shift

    def test_psi_always_nonnegative(self):
        baseline = {"a": 0.7, "b": 0.3}
        current = {"a": 0.4, "b": 0.6}
        psi = population_stability_index(baseline, current)
        assert psi >= 0


class TestDetectDrift:
    def test_stable_system(self):
        report = {
            "total": 1000,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.5, "mid_risk": 0.3, "high_risk": 0.2},
                "final_judgment": {"not_exist_violation": 0.6, "exist_violation": 0.4},
                "handling_suggestion": {"ignore": 0.5, "warning": 0.3, "limit_account": 0.15, "ban_account": 0.05},
            },
            "input_distribution": {
                "gift_total_value": {"count": 1000, "min": 0, "p50": 200, "p95": 5000, "max": 20000, "mean": 800},
            },
        }
        result = detect_drift(report, report)
        assert result.status == "stable"

    def test_drift_detected(self):
        baseline = {
            "total": 1000,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.6, "mid_risk": 0.3, "high_risk": 0.1},
                "final_judgment": {"not_exist_violation": 0.7, "exist_violation": 0.3},
                "handling_suggestion": {"ignore": 0.6, "warning": 0.25, "limit_account": 0.1, "ban_account": 0.05},
            },
            "input_distribution": {
                "gift_total_value": {"count": 1000, "min": 0, "p50": 200, "p95": 3000, "max": 10000, "mean": 500},
            },
        }
        current = {
            "total": 1000,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.2, "mid_risk": 0.3, "high_risk": 0.5},
                "final_judgment": {"not_exist_violation": 0.3, "exist_violation": 0.7},
                "handling_suggestion": {"ignore": 0.2, "warning": 0.2, "limit_account": 0.3, "ban_account": 0.3},
            },
            "input_distribution": {
                "gift_total_value": {"count": 1000, "min": 0, "p50": 5000, "p95": 20000, "max": 50000, "mean": 8000},
            },
        }
        result = detect_drift(current, baseline)
        assert result.status in ("drift_warning", "drift_critical")
        assert len(result.tests) > 0
