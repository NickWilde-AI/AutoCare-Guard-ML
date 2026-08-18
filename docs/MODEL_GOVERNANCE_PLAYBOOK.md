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
| model_version | `im-audit-judge-{base}-lora-v{N}` | `im-audit-judge-qwen3-32b-lora-v2` | 每次训练 |

> 说明：`im-audit-judge-qwen3-32b-lora-v*` 为**未来真实模型**的命名模板（对应 rollout.yaml 的 candidate 占位）；当前公开仓库的稳定版本名为 `heuristic-public-v0`（见 configs/model_registry.yaml）。
| prompt_version | `prompt-v{N}.{M}` | `prompt-v2.1` | prompt 修改 |
| rubric_version | `rubric-v{N}` | `rubric-v3` | 标注规范变更 |
| feature_schema_version | `schema-v{N}` | `schema-v1` | 输入字段变更 |
| postprocess_version | `post-v{N}` | `post-v2` | 路由规则变更 |

### 2.2 版本记录

所有版本信息通过 `configs/default.yaml` 中的 `versions` 字段管理，每次审计事件自动记录当时的版本快照。

## 3. 模型审批流程

### 3.1 前置条件

candidate 模型在申请晋升 stable 前必须满足：

| 检查项 | 阈值 | 验证方式 |
| --- | --- | --- |
| 整体 F1 | >= 0.78 | 离线 eval set |
| 误封率 FPR | < 3% | 离线 eval set |
| handling_macro_f1 | >= 0.70 | 离线 eval set |
| P95 推理延迟 | < 1200ms | benchmark_api |
| 回归测试 | 全部通过 | `make enterprise-check` |
| 灰度验证 | >= 24h 无告警 | 灰度日志 |

### 3.2 审批人

| 角色 | 职责 |
| --- | --- |
| 算法负责人 | 确认指标达标、评测报告无异常 |
| 安全策略 PM | 确认业务风险可接受 |
| SRE | 确认部署和性能无风险 |

### 3.3 审批记录

审批信息写入 `configs/model_registry.yaml`：

```yaml
models:
  im-audit-judge-qwen3-32b-lora-v2:
    status: stable
    approved_by: "算法负责人 + 安全策略 PM"
    approved_at: "2026-06-01"
    approval_ticket: "MODEL-APPROVE-2026-0601"
    metrics:
      final_judgment_acc: 0.821
      risk_macro_f1: 0.756
      handling_macro_f1: 0.732
      ban_account_fpr: 0.026
      p95_latency_ms: 680
```

## 4. 灰度发布

### 4.1 灰度策略

| 阶段 | 流量比例 | 持续时间 | 观察指标 |
| --- | --- | --- | --- |
| Shadow | 0%（仅记录不决策） | >= 24h | 输出分布、解析成功率 |
| Canary | 5% | >= 24h | ban_rate、F1、延迟 |
| 扩量 | 20% | >= 24h | 同上 + 人审反馈 |
| 全量 | 100% | - | 全量监控 |

### 4.2 灰度守护条件

任一条件触发则自动回滚到上一个 stable 版本：

- ban_rate 相对旧版上升 > 3pp
- parse_error_rate > 2%
- P95 延迟 > 1200ms
- 人工复核否决率 > 20%

### 4.3 灰度配置

```yaml
# configs/rollout.yaml
strategy: canary
canary_percent: 5
promote_after_hours: 24
auto_rollback_rules:
  - metric: ban_rate_delta
    threshold: 0.03
  - metric: parse_error_rate
    threshold: 0.02
  - metric: p95_latency_ms
    threshold: 1200
rollback_target: im-audit-judge-qwen3-32b-lora-v1
```

## 5. 回滚流程

### 5.1 触发条件

| 触发源 | 条件 | 响应时间 |
| --- | --- | --- |
| 自动告警 | 灰度守护条件任一触发 | 即时自动回滚 |
| 人工决策 | SRE 或算法负责人判断 | 5 分钟内 |
| 安全事件 | 发现严重漏放或误封 | 15 分钟内 |

### 5.2 回滚步骤

1. 更新 `model_registry.yaml` 中 candidate 状态为 retired
2. 确认 rollback_target 模型可用
3. 重启服务加载 stable 版本
4. 验证 `/ready` 返回正确版本号
5. 观察 10 分钟确认指标恢复
6. 创建事故记录（incident runbook）

## 6. 实验记录

### 6.1 实验模板

每次训练实验记录以下信息：

```yaml
experiment_id: "exp-2026-0607-001"
base_model: "Qwen/Qwen3-32B"
training_data:
  history_tickets: 24498
  synthetic: 11615
  refinement_hard: 2629
  public_binary: 12700
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
  final_judgment_acc: 0.821
  risk_macro_f1: 0.756
  handling_macro_f1: 0.732
  ban_account_fpr: 0.026
  training_loss_final: 0.42
notes: "LoRA r=16 在当前验证集上为效果与训练成本之间的折中选择。"
```

### 6.2 实验对比

使用 `im-guard ab-report` 命令生成两个模型的对比报告，输出包括：
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
