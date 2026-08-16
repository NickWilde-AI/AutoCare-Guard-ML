# Local data

The repository does not include real chat records or an internal test set. Put authorized and redacted JSONL files under `data/local/`; that directory is ignored by Git.

Minimal input shape:

```json
{"ticket_id":"local-example-id","chat_evidence_list":["redacted text"],"behavior_abnormal_list":[]}
```

See `src/im_guard_ml/schema.py` and `docs/TRAINING_AND_EVALUATION.md` for the complete schema and evaluation workflow.
