from im_guard_ml.build_dataset import dedupe_rows, normalize_xguard, split_rows, xguard_content


def test_xguard_safe_maps_to_safe_default():
    row = {
        "id": "safe-1",
        "sample_type": "general",
        "prompt": "正常聊天。",
        "response": "",
        "stage": "q",
        "label": "sec",
        "explanation": "safe",
    }

    result = normalize_xguard(row)

    assert result["label"]["final_judgment"] == "not_exist_violation"
    assert result["label"]["risk_level"] == "low_risk"
    assert result["label"]["handling_suggestion"] == "ignore"
    assert result["label"]["topic"] == "无主题"


def test_xguard_risk_maps_to_public_binary_warning_only():
    row = {
        "id": "risk-1",
        "sample_type": "general",
        "prompt": "诱导投资返利。",
        "response": "",
        "stage": "q",
        "label": "ec",
        "explanation": "economic crime",
    }

    result = normalize_xguard(row)

    assert result["task_type"] == "public_binary"
    assert result["label"]["final_judgment"] == "exist_violation"
    assert result["label"]["risk_level"] == "mid_risk"
    assert result["label"]["handling_suggestion"] == "warning"
    assert result["label"]["topic"] == "诈骗引流"
    assert result["label"]["handling_suggestion"] not in {"limit_account", "ban_account"}


def test_xguard_stage_text_joining():
    assert xguard_content({"stage": "q", "prompt": "question", "response": "answer"}) == "question"
    assert xguard_content({"stage": "r", "prompt": "question", "response": "answer"}) == "answer"
    assert xguard_content({"stage": "qr", "prompt": "question", "response": "answer"}) == (
        "[User Query] question\n\n[LLM Response] answer"
    )


def test_dedupe_rows_removes_duplicate_training_payloads():
    row = normalize_xguard({"prompt": "same", "stage": "q", "label": "sec"})
    duplicate = dict(row)
    duplicate["ticket_id"] = "different-id"

    assert len(dedupe_rows([row, duplicate])) == 1


def test_split_rows_creates_deterministic_train_val_test_splits():
    rows = [normalize_xguard({"prompt": str(i), "stage": "q", "label": "sec"}) for i in range(10)]

    first = split_rows(rows, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=7)
    second = split_rows(rows, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=7)

    assert {k: len(v) for k, v in first.items()} == {"train": 6, "val": 2, "test": 2}
    assert first == second
