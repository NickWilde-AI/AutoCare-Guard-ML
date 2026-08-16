# 风险策略与决策框架

本文档定义 IM 私聊风控审核系统的风险容忍度、决策标准、升级路径和人工复核机制。

## 1. 风险容忍度矩阵

| 风险等级 | 容忍度 | 业务含义 | 自动化处置 |
| --- | --- | --- | --- |
| `low_risk` | 高容忍 | 正常聊天或轻微擦边 | 自动放行（ignore） |
| `mid_risk` | 中等容忍 | 有违规倾向但证据不充分 | 警告或限制 + 人工采样复核 |
| `high_risk` | 零容忍 | 明确违规且行为异常 | 封禁账号 + 强制人工复核 |

## 2. 决策标准（Decision Criteria）

### 2.1 风险等级判定

```
IF 明确违规关键词 AND 行为异常（高频/大额/新用户）:
    risk_level = high_risk
ELIF 违规关键词存在 OR 行为异常（单一维度）:
    risk_level = mid_risk
ELSE:
    risk_level = low_risk
```

### 2.2 处置建议映射

| risk_level | final_judgment | handling_suggestion |
| --- | --- | --- |
| high_risk | exist_violation | ban_account |
| high_risk | exist_violation（证据单一） | limit_account |
| mid_risk | exist_violation | warning / limit_account |
| mid_risk | not_exist_violation | ignore |
| low_risk | * | ignore |

### 2.3 路由规则

| 条件 | 路由 | 原因 |
| --- | --- | --- |
| handling = ban_account | human_review_required | 最严处置必须人工确认 |
| risk_level = high 但 handling != ban | human_review_required | 高风险案件需要复核 |
| parse_status != ok | human_review_required | 模型输出解析异常，不信任 |
| 其他 | auto_close | 系统自动闭单 |

## 3. 升级路径（Escalation）

### Level 1：自动处置
- 系统根据模型输出 + 后处理规则自动执行
- 覆盖 ~90% 的审核工单
- SLO：P95 延迟 < 1200ms

### Level 2：人工复核
- 触发条件：ban_account、high_risk、解析异常
- 覆盖 ~8-10% 的工单
- SLA：4 小时内完成复核
- 复核结果回写审计日志

### Level 3：专家升级
- 触发条件：用户申诉、复核分歧、新型违规模式
- 覆盖 ~1-2% 的工单
- SLA：24 小时内出结论
- 需要安全策略团队介入

### Level 4：策略变更
- 触发条件：新政策法规、大规模误判、模型 drift 告警
- 责任人：安全策略 PM + 算法负责人
- 产出：rubric 更新 → 标注 → 重训 → 灰度

## 4. 安全红线（Hard Rules）

以下规则优先级高于模型输出，在 postprocess 层强制执行：

| 规则 | 逻辑 | 原因 |
| --- | --- | --- |
| 涉未成年人 | 强制 high_risk + ban_account | 法律合规零容忍 |
| 涉恐暴力 | 强制 high_risk + ban_account | 监管红线 |
| 模型输出 ban 但 risk < high | 修正 risk_level = high_risk | 逻辑一致性 |
| 模型输出 ignore 但 risk = high | 修正 handling = limit_account | 防止高风险漏放 |

## 5. 误判处理

### 5.1 误封（False Positive）

- 用户通过申诉通道提交
- 人工复核后标记 `override: false_positive`
- 自动解封 + 记入 hard case 池
- hard case 池满 100 条触发一次模型评估

### 5.2 漏放（False Negative）

- 用户举报或安全巡检发现
- 标记 `override: false_negative`
- 追加处置 + 记入 hard case 池
- 若同类漏放 > 5 例/天，触发 Level 4 策略变更

## 6. 阈值管理

### 6.1 告警阈值

| 指标 | warn | critical | 行动 |
| --- | --- | --- | --- |
| ban_rate | > 8% | > 12% | 暂停自动封禁，人工接管 |
| parse_error_rate | > 0.5% | > 2% | 检查模型输出格式，考虑回滚 |
| 空行为输入率 | > 5% | > 15% | 检查上游数据质量 |
| P95 延迟 | > 800ms | > 1200ms | 扩容或降级为规则引擎 |

### 6.2 阈值变更流程

1. 提出变更 PR，附带变更原因和影响分析
2. 安全策略 PM 审批
3. 灰度 5% 流量验证 24h
4. 全量生效 + 记录变更日志

## 7. 风险权衡

误判会带来用户体验和复核成本，漏判会带来安全风险。公开策略示例对 `mid_risk` 采用保守处置，对高影响动作强制人工复核，并通过 postprocess 一致性校验避免模型输出直接成为不可逆处罚。
