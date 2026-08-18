# 策略与阈值变更记录

本文档用于记录 rubric、处置阈值、路由策略、告警阈值和模型版本的变更。生产环境中，每次变更都应保留原因、影响面、回滚方式和验证结果。

| 日期 | 变更项 | 版本 | 原因 | 影响范围 | 验证方式 | 回滚方式 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06-06 | 接入 XGuard 公开数据映射 | rubric-v1 / feature-schema-v1 | 补充公开安全识别底座 | 训练数据构建，不影响强处置标签 | `audit-data` 通过，公开数据强处置泄漏为 0 | 移除 `--public-xguard` 输入 |
| 2026-06-06 | API 增加鉴权、限流、请求大小限制、审计查询 | postprocess-v1 | 提升生产化展示可信度 | FastAPI 服务入口 | `make test`，API 集成测试通过 | 清空对应环境变量或回退服务版本 |
| 2026-06-07 | 增加模型注册表和审批校验 | model-registry-v1 | 补齐模型治理最小闭环 | 模型版本、指标红线、回滚目标 | `model-registry-check` 通过 | 回退到 `current_stable` |
| 2026-08-19 | 统一口径对齐（2026-08-18 定稿） | prompt-v1 / rubric-v1 / feature-schema-v1 | 清理旧口径（Qwen3.5-27B、lr 2e-6、12 类主题、LoRA gate/up/down 目标层），统一为 Qwen3-32B LoRA 多任务 SFT、lr 1e-4、全局 Batch 64、11 类一级主题（赌博引流并入诈骗引流） | 配置、训练入口、主题体系、治理文档、实验记录 | `make enterprise-check` 通过（149 tests） | 回退对应 git commit |
| 2026-08-19 | 交叉审查修复（P1x17 + 代码类 P2） | postprocess-v2 / rubric-v1 | 修复训练 collator 不兼容、服务层接入 postprocess 三重保护、KS/AUPRC 并列失真、split 工单隔离、rubrics.yaml 运行时加载、限流内存清理、/metrics 计数分叉、guardrail 环境变量接线、P95 口径统一等 | src/tests/configs/deploy/docs | `make enterprise-check` 通过（183 tests） | 回退对应 git commit |

## 变更原则

- `ban_account` 相关策略必须经过人工复核闭环验证。
- 公开二分类数据不得训练 `limit_account` 或 `ban_account`。
- 每次模型、prompt、rubric、feature schema、postprocess 变更都必须带版本字段。
- 灰度阶段先 shadow，再小流量，再放量；异常时优先降级到规则引擎和人工复核。
