# 企业级成熟度评审报告

## 总体结论

当前项目提供售后风险研判与工单路由系统的脱敏工程骨架：多证据输入、结构化输出、解析兜底、策略路由、评测、监控、告警、版本追踪、API 服务、部署模板、契约门禁、环境 preflight、模型注册表示例和单元测试。公开实现适合技术交流和方案评审，不代表完整生产系统。

真实上线还需要内部业务数据、人工复核闭环、多实例持久化、网关级限流、真实集群灰度、权限治理、集中审计和长期监控。

## 成熟度分级

| 维度 | 当前状态 | 生产化展示评价 | 真实生产缺口 |
| --- | --- | --- | --- |
| 数据 | 示例数据 + XGuard 公开数据接入 | 已有冷启动公开安全底座 | 缺真实售后服务事件、申诉和人审样本 |
| 训练 | SFT 入口、LoRA 配置、公开样本保守归一 | 能说明训练链路和标签防污染 | 缺真实训练/验证/测试拆分和线上回流 |
| 测试 | 单元测试覆盖核心 schema、解析、后处理、评测、监控、API 安全、契约检查、生产 preflight、模型注册表和轻量压测脚本，GitHub Actions 自动运行 enterprise-check | 已补数据转换、API 集成测试、OpenAPI 契约门禁、压测脚本测试和远端质量门禁 | 缺真实多实例压测、网关压测和长时间 soak test |
| API | FastAPI、可选鉴权、request_id、请求限制、基础限流、审计落盘、OpenAPI 契约门禁 | 具备 demo 到服务化的关键桥梁，并能防止核心接口漂移 | 缺生产网关、租户隔离和网关级限流 |
| 安全 | Bearer Token、SHA-256 token hash、常量时间比较、最小角色权限、CORS 配置、公开数据不训练强处置、审计脱敏摘要 | 展示级安全边界明确，避免在生产化模板中直接保存明文 token | 缺企业密钥轮换、租户隔离和网关级 PII 策略 |
| 审计 | CLI 审计日志 + API JSONL/SQLite 审计后端 | 可追踪版本和研判结果，支持按 case/ticket 查询 | 缺归档、合规留存和跨实例集中查询 |
| 监控 | Prometheus 文本指标、延迟分位数、监控摘要、滑动窗口异常检测、drift 检测、SLO、告警规则 | 能展示核心研判指标意识 | 缺真实告警平台和实例维度聚合 |
| 部署 | vLLM 脚本、Dockerfile、Docker Compose、K8s 模板、env 示例、生产 preflight | 能讲清服务拆分和部署路径，并能机器检查关键生产配置 | 缺真实集群灰度发布自动化 |
| 模型治理 | model/prompt/rubric/schema/postprocess 版本、模型注册表、指标红线、回滚目标、灰度/A/B 配置、人审治理文档 | 具备版本追溯和最小审批治理意识 | 缺真实企业模型注册平台和线上 A/B 平台 |

## 已增强项

- 接入 `Alibaba-AAIG/XGuard-Train-Open-200K` 作为公开安全训练底座。
- 新增 XGuard 到项目标签体系的保守映射，避免公开数据污染 `expert_review` 和 `emergency_review`。
- 补齐 `dev` 和 `serve` 依赖中的 `pytest`、`httpx`。
- API 支持可选 Bearer Token、可配置 CORS、`request_id` 和 API 审计 JSONL。
- API 支持 `admin / writer / reader / auditor` 最小角色权限。
- API 支持请求大小限制、基础限流、结构化错误、`/ready` 和按 case/ticket 查询审计事件。
- API 支持 OpenAPI 契约导出和关键接口缺失检查，纳入 `enterprise-check`。
- 新增 API 使用说明，覆盖接口表、鉴权、错误码、审计查询和压测入口。
- 新增 `make benchmark-api` 和 `scripts/benchmark_api.py` 压测门禁，支持结果落盘、非 2xx 失败和 P95 延迟阈值检查。
- API 审计支持 `jsonl` 与 `sqlite` 两种后端，SQLite 后端建表并按主键索引查询。
- 审计事件记录脱敏输入摘要、payload hash 和 PII 类型，不落完整原文证据。
- Prometheus 指标增加风险等级、主题、动作建议和路由维度。
- Prometheus 指标增加延迟分位数，部署目录提供告警规则模板。
- CLI 增加 `window-alerts`，支持对批量预测结果做滑动窗口异常检测。
- CLI 增加 `drift-report`，支持相对历史 baseline 输出 PSI、卡方和 KS 漂移检测结果。
- 训练数据构建支持 train/val/test 拆分，数据审计增加基础 PII 风险扫描。
- 新增训练与评测流程文档，串联数据构建、审计、SFT、预测、评测报告、drift 和上线前检查。
- 测试增加 CLI pipeline 端到端覆盖，脚本增加本地 API 轻量压力测试工具。
- CLI 增加 `eval-report`，支持生成离线评测 Markdown 报告；新增策略与阈值变更记录模板。
- 新增人审复核、灰度和 A/B 治理配置与文档。
- 新增 K8s 部署模板，覆盖 ConfigMap、Secret、PVC、Deployment、Service 和健康探针。
- CLI 增加 `delivery-summary`，可生成企业级生产化交付摘要。
- CLI 增加 `readiness-check`，可机器检查核心交付物、忽略规则和本机公开数据状态。
- 文档补齐公开数据接入、API 安全配置和本地 UTF-8 locale 要求。
- 新增 GitHub Actions `enterprise-check`，push/PR 自动运行测试、编译、交付摘要和 readiness-check。
- 新增 `production-preflight`，上线前检查鉴权、CORS、审计、限流和请求大小配置。
- 新增 `model-registry-check`，校验 stable/candidate、审批元数据、指标红线和回滚目标。
- 新增压测脚本单元测试，覆盖成功率、延迟分位数、warmup 和阈值失败逻辑。

## 机器验收

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make enterprise-check
PYTHONPATH=src python3 -m autocare_guard_ml.cli readiness-check --project-root . --out outputs/readiness_check.json
make serve
make benchmark-api
```

`readiness-check` 的 `fail` 表示仓库核心交付物或忽略规则缺失；`warn` 主要表示本机未下载或未转换 XGuard 大数据文件。公开数据属于本机外部数据，不应提交到 git。

`make benchmark-api` 需要服务已启动，默认对 `/judge` 发送 100 次请求，生成 `outputs/api_benchmark.json`，并在非 2xx 响应或 P95 超过 1200ms 时失败。它是本地展示级性能门禁，不替代真实多实例压测。

## 下一阶段建议

1. 引入真实或人工审核过的售后服务事件样本，建立固定 eval set。
2. 将 SQLite 审计升级为 PostgreSQL 或日志平台集中查询。
3. 增加生产网关、密钥轮换和集中权限系统。
4. 将 K8s 模板接入真实集群灰度发布、网关压测、多实例压测和长时间 soak test。
5. 将当前最小模型注册表接入企业模型注册、审批和 A/B 平台。

## 对外表述

可以把当前项目定位为：面向新能源汽车售后风险智能研判与工单路由的生产化展示项目。它已经证明完整工程链路、公开安全数据接入、保守动作策略和服务化治理能力；但真实企业上线仍需要业务私有数据、人审闭环和平台级部署治理。
