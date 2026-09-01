# 数据接入规范

本文档定义 AutoCare 售后风险研判系统如何对接上游数据源，包括接入协议、字段规范、质量约束和运维要求。

## 1. 数据源总览

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  售后 / 工单  │────▶│  证据聚合    │────▶│  研判服务         │
│  后端        │     │  (Kafka/HTTP)│     │  (POST /judge)   │
└──────────────┘     └──────────────┘     └──────────────────┘
       │                    │
       ▼                    ▼
  服务对话流           车辆 / 故障特征服务
  (conversation)       (vehicle / fault)
```

## 2. 接入协议

### 2.1 实时接入（推荐）

| 参数 | 值 |
| --- | --- |
| 协议 | HTTP POST (JSON) / gRPC |
| 端点 | `/judge` |
| 超时 | 客户端 3s，服务端 5s |
| 重试 | 最多 1 次，间隔 500ms |
| 幂等 | 基于 `case_id` 去重（legacy 输入字段 `ticket_id` 仍兼容） |

### 2.2 批量接入（离线评测）

| 参数 | 值 |
| --- | --- |
| 格式 | JSONL 文件 |
| 命令 | `autocare-guard predict data/input.jsonl` |
| 场景 | 离线评测、回溯研判、数据回流 |

## 3. 输入字段规范

### 3.1 推荐必填字段

| 字段 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| `case_id` | string | 服务事件唯一 ID | `"ac-20260607-0001"` |
| `conversation_evidence` | list[object] | 服务对话证据（已脱敏） | `[{"role":"owner","text":"充电中闻到焦糊味"}]` |

### 3.2 推荐可选字段

| 字段 | 类型 | 说明 | 缺失时行为 |
| --- | --- | --- | --- |
| `vehicle_signal_summary` | dict | 车辆信号摘要（行驶/充电状态、告警、热状态等） | 视为无车辆信号；紧急动作会被门禁拦截 |
| `fault_evidence` | list[object] | 故障 / 域告警证据 | 视为无故障证据 |
| `service_history_summary` | dict | 服务历史摘要（重复维修、未结工单等） | 视为无历史 |
| `service_context` | dict | 渠道 / 场景上下文 | 默认空对象 |
| `vehicle_context` | dict | 车型 / VIN 摘要等（脱敏） | 默认空对象 |
| `missing_and_conflicts` | dict | 上游已知缺失与冲突 | 默认空对象 |

### 3.3 legacy 输入字段兼容

若上游仍使用旧字段名，服务端会映射到 AutoCare 字段：

| legacy 字段 | 映射到 |
| --- | --- |
| `ticket_id` | `case_id` |
| `chat_evidence_list` | `conversation_evidence` |
| `audit_scene` | `service_context` |
| `behavior_abnormal_list` | 可落入 `fault_evidence` 等结构化侧（训练归一时） |

新接入请直接使用 AutoCare 字段，不要继续扩展 legacy 字段。

### 3.4 车辆 / 故障特征对接示例

```json
{
  "case_id": "ac-20260607-0001",
  "conversation_evidence": [
    {"role": "owner", "text": "充电中闻到焦糊味，车机提示高压异常。"}
  ],
  "vehicle_signal_summary": {
    "motion_state": "charging",
    "alert_summary": ["高压系统告警"],
    "thermal_status": "abnormal_rise"
  },
  "fault_evidence": [
    {"domain": "hv_system", "severity": "critical", "count": 2}
  ],
  "service_history_summary": {
    "repeat_repair_count": 0,
    "open_work_orders": 0
  }
}
```

车辆 / 故障特征服务建议提供：

- 行驶 / 充电 / 停放状态
- 高压、热安全、制动、动力等域告警摘要
- 故障码域与严重度聚合（脱敏）
- 近期服务历史（重复维修、未结工单）
- 已知缺失与冲突说明

## 4. 数据质量约束

### 4.1 上游 SLA

| 指标 | 要求 | 降级策略 |
| --- | --- | --- |
| 可用性 | > 99.9% | 降级为对话 + 已有车辆摘要研判；无车辆侧证据时禁止直接紧急动作 |
| 延迟 | P95 < 50ms（证据聚合） | 超时则不等待车辆 / 故障特征 |
| 数据完整性 | `case_id` 与对话证据必填 | 缺失则拒绝并返回 422 |

### 4.2 输入校验规则

```python
# 在 /judge 端点入口执行
assert case_id is not None and len(case_id) > 0
assert conversation_evidence is not None and len(conversation_evidence) > 0
assert total_payload_bytes <= MAX_REQUEST_BYTES  # 默认 256KB
```

### 4.3 数据脱敏要求

上游在发送前必须完成以下脱敏：

- 手机号 → `1**********`
- 身份证号 → `***`
- 银行卡号 → `****`
- 真实姓名 → 保留姓氏 + `**`
- VIN / 车牌等标识 → 按企业脱敏策略摘要

研判服务不应接收未脱敏的 PII。若检测到 PII 模式（见 `privacy.py`），将在审计日志中标记但不阻断请求。

## 5. 批量数据处理

### 5.1 训练数据收集

```
每日定时任务（T+1）
  → 从审计日志导出前一天已闭单的服务事件
  → 人工复核过的标记为 internal 来源
  → 自动关闭的标记为 auto_labeled 来源
  → 写入 data/train/daily/ 目录
```

### 5.2 数据回流条件

| 来源 | 入选条件 | 标签来源 |
| --- | --- | --- |
| 人工复核 | reviewer 确认的最终研判 | 人工标注 |
| 车主申诉 / 客诉纠正 | 确认误判 | 修正标签 |
| hard case | committee 分歧 > 阈值 | 专家标注 |
| 漏判补录 | 巡检 / 救援复盘确认风险事件 | 补充标注 |

## 6. 监控与告警

### 6.1 接入层监控

| 指标 | 含义 | 告警阈值 |
| --- | --- | --- |
| 请求量 QPS | 系统负载 | 突增 3x 触发扩容 |
| 空证据比例 | 上游异常 | > 5% 告警 |
| 超大 payload 比例 | 异常请求 | > 1% 告警 |
| `case_id` 重复率 | 重复提交 | > 2% 告警 |
| 车辆侧证据缺失率 | 上游特征异常 | 见 `configs/default.yaml` 的 `missing_vehicle_evidence_rate_*` |

### 6.2 数据质量日报

每日自动生成数据质量报告（`autocare-guard audit-data`），检查：

- 字段缺失率
- 标签分布偏移
- 重复样本比例
- PII 泄露风险

## 7. 部署模式与接入差异

| 模式 | 接入方式 | 适用场景 |
| --- | --- | --- |
| 本地 demo | CLI 直接读取 JSONL | 开发调试 |
| 单机服务 | HTTP POST /judge | 验证和压测 |
| 生产部署 | 网关 → 负载均衡 → 研判服务集群 | 线上流量 |

生产部署时，建议在网关层完成：

- 请求鉴权（API Gateway token 校验）
- 全局限流（基于租户 / 业务线）
- 请求路由（按场景分发）
- 请求日志（access log 独立于审计日志）
