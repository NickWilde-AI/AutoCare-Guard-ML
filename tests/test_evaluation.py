"""Tests for evaluation metrics."""

import pytest

from im_guard_ml.evaluation import (
    auprc,
    eval_binary,
    eval_multi_field,
    fleiss_kappa,
    macro_f1,
    ordinal_krippendorff_alpha,
)


class TestEvalBinary:
    def test_perfect_predictions(self):
        targets = [1, 1, 0, 0, 1, 0]
        preds = [1, 1, 0, 0, 1, 0]
        result = eval_binary(targets, preds)
        assert result["accuracy"] == 1.0
        assert result["f1"] == 1.0
        assert result["fpr"] == 0.0

    def test_all_wrong(self):
        targets = [1, 1, 0, 0]
        preds = [0, 0, 1, 1]
        result = eval_binary(targets, preds)
        assert result["accuracy"] == 0.0
        assert result["fpr"] == 1.0

    def test_with_probabilities(self):
        targets = [1, 1, 0, 1, 0]
        preds = [1, 0, 0, 1, 0]
        probs = [0.9, 0.4, 0.1, 0.8, 0.2]
        result = eval_binary(targets, preds, probs)
        assert result["auprc"] is not None
        assert 0.0 <= result["auprc"] <= 1.0

    def test_without_probabilities(self):
        targets = [1, 0, 1]
        preds = [1, 0, 0]
        result = eval_binary(targets, preds)
        assert result["auprc"] is None


class TestMacroF1:
    def test_perfect_predictions(self):
        targets = ["a", "b", "c", "a", "b", "c"]
        preds = ["a", "b", "c", "a", "b", "c"]
        labels = ["a", "b", "c"]
        assert macro_f1(targets, preds, labels) == 1.0

    def test_partial_correct(self):
        targets = ["a", "a", "b", "b"]
        preds = ["a", "b", "b", "a"]
        labels = ["a", "b"]
        result = macro_f1(targets, preds, labels)
        assert 0.0 < result < 1.0


class TestEvalMultiField:
    def test_basic_evaluation(self):
        targets = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account"},
            {"risk_level": "low_risk", "handling_suggestion": "ignore"},
        ]
        preds = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account"},
            {"risk_level": "low_risk", "handling_suggestion": "ignore"},
        ]
        metas = [{"topic": "代刷/包榜"}, {"topic": "无主题"}]
        result = eval_multi_field(targets, preds, metas)
        assert result["risk_per_topic_acc"]["代刷/包榜"] == 1.0
        assert result["risk_per_topic_acc"]["无主题"] == 1.0

    def test_partial_correct(self):
        targets = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account"},
            {"risk_level": "mid_risk", "handling_suggestion": "warning"},
        ]
        preds = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account"},
            {"risk_level": "low_risk", "handling_suggestion": "ignore"},
        ]
        result = eval_multi_field(targets, preds)
        assert 0.0 < result["risk_macro_f1"] < 1.0


class TestFleissKappa:
    def test_perfect_agreement(self):
        # All raters agree on all items
        matrix = [
            [3, 0, 0],
            [0, 3, 0],
            [0, 0, 3],
            [3, 0, 0],
        ]
        kappa = fleiss_kappa(matrix)
        assert kappa > 0.9

    def test_moderate_agreement(self):
        # Partial agreement
        matrix = [
            [3, 0, 0, 0],
            [0, 2, 1, 0],
            [0, 0, 1, 2],
            [0, 0, 0, 3],
        ]
        kappa = fleiss_kappa(matrix)
        assert 0.3 < kappa < 0.9


class TestOrdinalKrippendorffAlpha:
    def test_perfect_agreement(self):
        annotations = [
            [1, 2, 3, 1, 2, 3],
            [1, 2, 3, 1, 2, 3],
            [1, 2, 3, 1, 2, 3],
        ]
        alpha = ordinal_krippendorff_alpha(annotations)
        assert alpha > 0.95

    def test_with_none(self):
        annotations = [
            [1, 2, None, 3],
            [1, 2, 3, 3],
            [1, None, 3, 3],
        ]
        alpha = ordinal_krippendorff_alpha(annotations)
        assert -1.0 <= alpha <= 1.0

    def test_reported_range(self):
        # Design doc reports alpha = 0.71
        annotations = [
            [1, 2, 3, 3, 2, 1],
            [1, 2, 3, 2, 2, 1],
            [1, 1, 3, 3, 2, 1],
        ]
        alpha = ordinal_krippendorff_alpha(annotations)
        assert 0.5 < alpha < 0.9
