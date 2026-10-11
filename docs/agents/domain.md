# 领域与架构文档消费规范 (Domain Docs)

定义工程化技能在探索本代码库时，如何消费本项目的领域文档与架构决策记录。

## 探索代码库前的强制阅读规则

1. **`CONTEXT.md`**：位于仓库根目录的核心领域模型与术语定义；
2. **`CONTEXT-MAP.md`**：位于仓库根目录的限界上下文映射图（多上下文大型工程使用）；
3. **`docs/adr/`**：架构决策记录目录（Architecture Decision Records）。涉及相关模块前，阅读触及该模块的历史 ADR。

> 💡 **静默宽容原则**：若上述文档尚不存在，请**静默继续推进工作**，无需报错，也无需主动要求预先创建。`/domain-modeling` 技能会在术语和决策真正达成一致时按需延迟创建它们。

## 目录拓扑结构

本项目采用**单上下文（Single-context）标准结构**：

```text
/
├── CONTEXT.md          # 核心领域模型与术语词汇表
├── docs/adr/           # 架构决策记录 (ADR)
│   ├── 0001-hybrid-connection-pool.md
│   ├── 0002-soft-timeout-and-drain-buffer.md
│   ├── 0003-runtime-configuration-and-security-posture.md
│   ├── 0004-release-artifacts-and-distribution-pipeline.md
│   └── 0005-full-duplex-buffering-and-security-hardening.md
└── src/                # 源码目录

```

## 严格遵循统一词汇表 (Glossary)

在生成任何交付物（Issue 标题、重构方案、代码假设、测试用例命名、函数定义）时，**必须统一使用 `CONTEXT.md` 中定义的专业术语**，严禁使用词汇表中已明确规避的近义词或生僻混淆词。

若所需的核心概念尚未在词汇表中定义，这是一个明确信号：要么当前正在发明项目未约定的非标词汇（需重新评估），要么领域模型存在缺失（应触发 `/domain-modeling` 补充）。

## 架构决策冲突告警 (ADR Conflicts)

若你的方案或代码实现与既有 ADR 存在冲突，必须在显式位置明确提出，严禁静默覆盖已有架构决策：

> ⚠️ *该方案与 ADR-0001 (混合连接池模型) 存在冲突，但建议重新评估此决策，原因在于……*
