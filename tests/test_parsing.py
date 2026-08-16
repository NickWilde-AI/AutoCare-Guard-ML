"""Tests for JSON parsing and fallback logic."""

import pytest

from im_guard_ml.parsing import parse_judge_output


class TestParseJudgeOutput:
    def test_valid_json(self):
        text = '{"risk_level": "high_risk", "topic": "代刷/包榜", "correlation_analysis": "test", "final_judgment": "exist_violation", "judgment_basis": "test", "handling_suggestion": "ban_account"}'
        result = parse_judge_output(text)
        assert result["risk_level"] == "high_risk"
        assert result["final_judgment"] == "exist_violation"
        assert result["handling_suggestion"] == "ban_account"
        assert result["topic"] == "代刷/包榜"

    def test_json_with_surrounding_text(self):
        text = 'Here is my analysis:\n{"risk_level": "mid_risk", "topic": "私下交易", "correlation_analysis": "", "final_judgment": "exist_violation", "judgment_basis": "", "handling_suggestion": "warning"}\nDone.'
        result = parse_judge_output(text)
        assert result["risk_level"] == "mid_risk"
        assert result["handling_suggestion"] == "warning"

    def test_regex_fallback(self):
        # Malformed JSON but contains enum values
        text = 'risk_level is high_risk and final_judgment is exist_violation with ban_account'
        result = parse_judge_output(text)
        assert result["risk_level"] == "high_risk"
        assert result["final_judgment"] == "exist_violation"
        assert result["handling_suggestion"] == "ban_account"

    def test_empty_input(self):
        result = parse_judge_output("")
        assert result["risk_level"] == "low_risk"
        assert result["final_judgment"] == "not_exist_violation"
        assert result["handling_suggestion"] == "ignore"

    def test_garbage_input(self):
        result = parse_judge_output("completely random garbage text 12345")
        assert result["risk_level"] == "low_risk"
        assert result["final_judgment"] == "not_exist_violation"
        assert result["handling_suggestion"] == "ignore"

    def test_partial_json(self):
        # JSON with missing closing brace - should fall back to regex
        text = '{"risk_level": "mid_risk", "final_judgment": "exist_violation"'
        result = parse_judge_output(text)
        # Should at least extract via regex
        assert result["risk_level"] == "mid_risk"
        assert result["final_judgment"] == "exist_violation"

    def test_validation_correction_ban_without_high(self):
        # ban_account without high_risk should be corrected
        text = '{"risk_level": "mid_risk", "topic": "无主题", "correlation_analysis": "", "final_judgment": "exist_violation", "judgment_basis": "", "handling_suggestion": "ban_account"}'
        result = parse_judge_output(text)
        # Should be corrected to limit_account
        assert result["handling_suggestion"] == "limit_account"

    def test_not_violation_forces_safe_handling(self):
        text = '{"risk_level": "mid_risk", "topic": "无主题", "correlation_analysis": "", "final_judgment": "not_exist_violation", "judgment_basis": "", "handling_suggestion": "limit_account"}'
        result = parse_judge_output(text)
        # not_exist_violation should force low_risk + ignore
        assert result["risk_level"] == "low_risk"
        assert result["handling_suggestion"] == "ignore"
