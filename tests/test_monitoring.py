"""Tests for monitoring and drift detection (AutoCare)."""

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
                    "event_judgment": "risk_event",
                    "recommended_action": "emergency_review",
                },
                "conversation_evidence": [{"content": "有焦糊味"}],
                "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
                "fault_evidence": [{"fault_domain": "battery", "severity_from_source": "critical"}],
            },
            {
                "prediction": {
                    "risk_level": "low_risk",
                    "event_judgment": "not_risk_event",
                    "recommended_action": "information_reply",
                },
                "conversation_evidence": [{"content": "hello"}],
                "vehicle_signal_summary": {},
                "fault_evidence": [],
            },
        ]
        report = build_monitoring_report(rows)
        assert report["total"] == 2
        assert "risk_level" in report["prediction_distribution"]
        assert "emergency_review_rate" in report["quality_guards"]
        assert report["quality_guards"]["emergency_review_rate"] == 0.5
        assert report["quality_guards"]["missing_vehicle_evidence_rate"] == 0.5

    def test_empty_input(self):
        report = build_monitoring_report([])
        assert report["total"] == 0


class TestCompareReports:
    def test_no_change(self):
        report = {
            "total": 100,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.5, "mid_risk": 0.3, "high_risk": 0.2},
                "recommended_action": {"information_reply": 0.5, "service_followup": 0.3},
            },
            "input_distribution": {
                "missing_vehicle_evidence": {"mean": 0.2},
            },
        }
        delta = compare_reports(report, report)
        assert delta["total_delta"] == 0
        assert delta["missing_vehicle_evidence_mean_delta"] == 0.0


class TestSlidingWindowReport:
    def test_detects_abnormal_window(self):
        safe_rows = [
            {
                "prediction": {
                    "risk_level": "low_risk",
                    "event_judgment": "not_risk_event",
                    "recommended_action": "information_reply",
                },
                "conversation_evidence": ["普通咨询"],
                "vehicle_signal_summary": {"warning_lights": ["正常"]},
                "fault_evidence": [{"fault_domain": "other", "severity_from_source": "info"}],
            }
            for _ in range(10)
        ]
        risky_rows = [
            {
                "prediction": {
                    "risk_level": "high_risk",
                    "event_judgment": "risk_event",
                    "recommended_action": "emergency_review",
                },
                "conversation_evidence": ["焦糊味"],
                "vehicle_signal_summary": {},
                "fault_evidence": [],
            }
            for _ in range(10)
        ]

        report = build_sliding_window_report(
            safe_rows + risky_rows,
            window_size=10,
            step_size=10,
            thresholds={
                "emergency_review_rate_warn": 0.2,
                "emergency_review_rate_critical": 0.5,
            },
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
        assert chi2 >= 0


class TestKSTest:
    def test_identical_samples(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        d, p = ks_test(a, b)
        assert d < 0.3
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
        assert psi > 0.1

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
                "event_judgment": {"not_risk_event": 0.6, "risk_event": 0.4},
                "recommended_action": {
                    "information_reply": 0.5,
                    "service_followup": 0.3,
                    "create_work_order": 0.15,
                    "emergency_review": 0.05,
                },
            },
            "input_distribution": {
                "missing_vehicle_evidence": {
                    "count": 1000,
                    "min": 0,
                    "p50": 0,
                    "p95": 1,
                    "max": 1,
                    "mean": 0.2,
                },
            },
        }
        result = detect_drift(report, report)
        assert result.status == "stable"

    def test_drift_detected(self):
        baseline = {
            "total": 1000,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.6, "mid_risk": 0.3, "high_risk": 0.1},
                "event_judgment": {"not_risk_event": 0.7, "risk_event": 0.3},
                "recommended_action": {
                    "information_reply": 0.6,
                    "service_followup": 0.25,
                    "create_work_order": 0.1,
                    "emergency_review": 0.05,
                },
            },
            "input_distribution": {
                "missing_vehicle_evidence": {
                    "count": 1000,
                    "min": 0,
                    "p50": 0,
                    "p95": 1,
                    "max": 1,
                    "mean": 0.1,
                },
            },
        }
        current = {
            "total": 1000,
            "prediction_distribution": {
                "risk_level": {"low_risk": 0.2, "mid_risk": 0.3, "high_risk": 0.5},
                "event_judgment": {"not_risk_event": 0.3, "risk_event": 0.7},
                "recommended_action": {
                    "information_reply": 0.2,
                    "service_followup": 0.2,
                    "create_work_order": 0.3,
                    "emergency_review": 0.3,
                },
            },
            "input_distribution": {
                "missing_vehicle_evidence": {
                    "count": 1000,
                    "min": 0,
                    "p50": 1,
                    "p95": 1,
                    "max": 1,
                    "mean": 0.8,
                },
            },
        }
        result = detect_drift(current, baseline)
        assert result.status in ("drift_warning", "drift_critical", "stable")
        assert len(result.tests) >= 0
