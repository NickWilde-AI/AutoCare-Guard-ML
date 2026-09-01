# 模型治理 Playbook

本文档面向算法工程师和运维人员，描述模型从训练到退役的全生命周期治理流程。

## 1. 模型生命周期

```
训练完成 → candidate → 离线评测 → 审批 → 灰度 → stable → 退役 retired
                ↑                                         │
                └──── 回滚 ←──── 告警触发 ←───────────────┘
```

### 状态定义

| 状态 | 含义 | 允许操作 |
| --- | --- | --- |
| `candidate` | 候选模型，尚未通过审批 | 离线评测、shadow 推理 |
| `stable` | 当前线上服务模型 | 接收生产流量 |
| `retired` | 已退役，不再服务 | 仅供审计查询 |

## 2. 版本管理

### 2.1 版本号体系

| 版本类型 | 格式 | 示例 | 变更频率 |
| --- | --- | --- | --- |
| model_version | `autocare-risk-judge-{base}-lora-v{N}` | `autocare-risk-judge-qwen3-32b-lora-v2` | 每次训练 |

> 说明：`autocare-risk-judge-qwen3-32b-lora-v*` 为未来真实模型的命名模板（对应 `rollout.yaml` 的 candidate 占位）；当前公开仓库的稳定版本名为 `heuristic-public-v0`（见 `configs/model_registry.yaml`）。

| prompt_version | `prompt-autocare-v{N}` | `prompt-autocare-v1` | prompt 修改 |
| rubric_version | `rubric-autocare-v{N}` | `rubric-autocare-v1` | 标注规范变更 |
| feature_schema_version | `feature-schema-autocare-v{N}` | `feature-schema-autocare-v1` | 输入字段变更 |
| postprocess_version | `postprocess-autocare-v{N}` | `postprocess-autocare-v1` | 路由规则变更 |

### 2.2 版本记录

所有版本信息通过 `configs/default.yaml` 中的 `versions` 字段管理，每次审计事件自动记录当时的版本快照。

## 3. 模型审批流程

### 3.1 前置条件

candidate 模型在申请晋升 stable 前必须满足（阈值结构见 `configs/model_registry.yaml` 注释示例与 `configs/rollout.yaml` guardrails；**公开仓库不宣称已达到任何生产评测数字**）：

| 检查项 | 参考红线来源 | 验证方式 |
| --- | --- | --- |
| 事件研判 F1 | 注册表 `promotion_guardrails`（晋升时填写真实评测） | 离线 eval set |
| `emergency_review_fpr` | `configs/rollout.yaml`：`<= 0.03` | 离线 eval set |
| handling macro-F1 | 注册表 `promotion_guardrails`（晋升时填写真实评测） | 离线 eval set |
| `parse_non_ok_rate` | `configs/rollout.yaml`：`<= 0.02` | 离线 / 线上监控 |
| P95 推理延迟 | `configs/rollout.yaml`：`<= 1200ms` | `benchmark_api` |
| 回归测试 | 全部通过 | `make enterprise-check` |
| 灰度验证 | >= 24h 无告警 | 灰度日志 |

### 3.2 审批人

| 角色 | 职责 |
| --- | --- |
| 算法负责人 | 确认指标达标、评测报告无异常 |
| 售后安全策略 PM | 确认业务风险可接受 |
| SRE | 确认部署和性能无风险 |

### 3.3 审批记录

审批信息写入 `configs/model_registry.yaml`。公开示例如下（`metrics` 为空表示不构成质量声明）：

```yaml
models:
  - model_version: heuristic-public-v0
    status: stable
    approved_by: public-example
    approved_at: not-applicable
    metrics: {}
    notes: "Deterministic public rule baseline for engineering verification only."
```

真实候选模型晋升时，应取消 `promotion_guardrails` 注释并填入**真实评测数字**后再跑 `model-registry-check`。

## 4. 灰度发布

### 4.1 灰度策略

| 阶段 | 流量比例 | 持续时间 | 观察指标 |
| --- | --- | --- | --- |
| Shadow | 1%（只记录） | >= 24h | 输出分布、解析成功率 |
| Canary / small | 10% | >= 24h | 紧急动作占比、F1、延迟 |
| 扩量 / ramp | 50% | >= 24h | 同上 + 人审反馈 |
| 全量 | 100% | - | 全量监控 |

### 4.2 灰度守护条件

任一条件触发则自动回滚到上一个 stable 版本（见 `configs/rollout.yaml`）：

- `emergency_review_fpr > 0.03`
- `parse_non_ok_rate > 0.02`
- P95 延迟 > 1200ms
- 人工复核否决率异常升高

### 4.3 灰度配置

```yaml
# configs/rollout.yaml（节选）
rollout:
  default_stage: shadow
  stages:
    small:
      traffic_percent: 10
      model_actions: ["information_reply", "collect_more_evidence", "service_followup", "create_work_order_candidate"]
      emergency_requires_human_review: true
ab_test:
  guardrails:
    emergency_review_fpr_max: 0.03
    parse_non_ok_rate_max: 0.02
    p95_latency_ms_max: 1200
```

## 5. 回滚流程

### 5.1 触发条件

| 触发源 | 条件 | 响应时间 |
| --- | --- | --- |
| 自动告警 | 灰度守护条件任一触发 | 即时自动回滚 |
| 人工决策 | SRE 或算法负责人判断 | 5 分钟内 |
| 安全事件 | 发现严重漏判或误升级 | 15 分钟内 |

### 5.2 回滚步骤

1. 更新 `model_registry.yaml` 中 candidate 状态为 retired
2. 确认 rollback target 模型可用
3. 重启服务加载 stable 版本
4. 验证 `/ready` 返回正确版本号
5. 观察 10 分钟确认指标恢复
6. 创建事故记录（incident runbook）

## 6. 实验记录

### 6.1 实验模板

每次训练实验记录以下信息（样本量为占位字段，需填入真实实验数据，**不要把占位值写成生产结论**）：

```yaml
experiment_id: "exp-YYYYMMDD-001"
base_model: "Qwen/Qwen3-32B"
training_data:
  history_cases: <count>
  synthetic: <count>
  refinement_hard: <count>
  public_binary: <count>
hyperparameters:
  # 统一口径（2026-08-18 定稿）：LoRA 多任务 SFT，lr 1e-4，2 Epoch，全局 Batch 64。
  learning_rate: 0.0001
  epochs: 2
  lora_rank: 16
  lora_alpha: 32
  lora_dropout: 0.05
  target_modules: [q_proj, k_proj, v_proj, o_proj]
  batch_size: 64
  max_seq_length: 8192
results:
  event_judgment_f1: <fill-from-eval>
  risk_macro_f1: <fill-from-eval>
  handling_macro_f1: <fill-from-eval>
  emergency_review_fpr: <fill-from-eval>
  training_loss_final: <fill-from-run>
notes: "记录本轮数据版本、硬件与结论边界。"
```

### 6.2 实验对比

使用 `autocare-guard ab-report` 命令生成两个模型的对比报告，输出包括：

- 各指标 delta
- 分类别 F1 对比
- 典型分歧案例

## 7. 退役流程

模型退役前确认：

- 已有新 stable 版本替代
- 审计日志中标记退役时间
- checkpoint 文件保留 90 天后可删除
- 退役原因写入 registry

## 8. 治理检查命令

```bash
# 模型注册表合规校验
make model-registry-check

# 生产上线前全量自检
make production-preflight

# 查看当前版本
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/ready
```
