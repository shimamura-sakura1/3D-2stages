# Governed S0 迁移说明

依据 D:/contract-govern skill 的 README、v3 构建指南、SPEC、MIGRATE/EVOLVE、验证器、实际 I/O runner 和版本验收代码建立。保留 runtime/providers/contracts/policies/prompts/templates 目录和已有生产行为，没有复制一套新的 Agent Runtime。

## 理解与采用

参考项目由现有 Agent 负责语义决策，skillctl 负责确定性登记、影响分析、执行证据和验收。SKILL.md 是编排入口，interface.json 是文件与真实接口的登记表。tests/manifest.json 分开记录 covers、exercises 和 depends_on_artifacts。验收同时要求声明契约和实际 I/O 通过，成功后才生成 changes。

迁移前运行原有 95 项测试，通过；随后增加真实 CLI 子进程 characterization，记录规划、资产获取、审核拒绝、MCP 准备和资产交付行为，结果见 baseline.json。之后才修改 Schema 引用和直接脚本入口。新增结构审计测试先因工具/fixture 不存在失败，再实现工具与实际数据。

## 必要改动

- SKILL.md 增加可解析的六步 Execution Router，保留 MCP、SSH、审核和返工约定。
- runtime/cli.py 支持具体文件路径调用及原有 python -m 入口，便于登记真实绑定。
- 生产 JSON Schema 移除虚拟 HTTPS 标识并改用相对引用；runtime/validators.py 通过本地文件 URI registry 解析。没有改变生产字段、状态或数据版本。
- scripts/check_contracts.py 是新的确定性结构审计工具。输入一个完整的七类样本文档包，先校验所有文档再输出对应 JSON；它不批准资产，不检查模型文件存在，也不运行 Blender/HY3D。
- scripts/govern.py 对源码投影运行原有 skillctl，排除实际资产、依赖缓存和临时报告，检测验证期间的源码变化，保留原工具生成的证据记录。

## 如实表达验证能力

两个公开 subprocess binding 是生产 CLI 的 init I/O 和结构审计工具。生产 CLI 的其他子命令由实际 CLI characterization 与历史回归覆盖，不宣称所有子命令都返回同一种 Schema。

七类生产 Schema 在真实审计输出上逐个验证；审计包、CLI 参数及错误 Schema 也直接用于 binding。测试记录包含实际输入、stdout/stderr、退出码及输出内容，不把静态 Schema 合法性视为运行成功。

参考框架 0.1 没有“内部库模块”或“宿主 MCP 工具”的独立 enforcement 类型。因此内部 runtime 库、固定 Blender 工作者和辅助配置作为 advisory 依赖节点登记，并在描述中说明真实角色；公共 CLI 仍执行这些库的硬性约束。它们不是虚构的独立 subprocess，也不被用作 active requirement 的唯一实现依据。回归的 exercises 仍登记实际使用的内部模块，影响图沿真实 import/read 关系传播。

docs/workflow.md 作为 Agent procedure 登记；测试实际读取并执行其中的命令数组样例。这个证据只证明可执行文档示例，不证明 Agent 理解全部自然语言或具有美术判断能力。原 prompts 保留为规划/审查建议。REQ-ART-001 保持 unresolved，等待真实 Agent/用户场景评审。

REQ-LIVE-001 也保持 unresolved：Blender MCP 插件最近不可达，远程 HY3D 服务器尚未准备。模拟进程、HTTP 回环服务和源码结构测试不能替代真实 GPU 推理或场景渲染。

## 静态警告审查

路由评分是显式数值政策，语义/风格评分由人或 Agent 提供，代码不假装理解自然语言。local_library 的分词仅做目录关键词匹配；SSH、资产 ID 和路径的正则用于语法限制。默认值如 plan_only、MCP、重试次数来自已有正式约定。CLI 中 --catalog/--hy3d-config 未指定不会静默执行外部服务。潜在 silent-default 警告需要结合这些测试和声明审查，不能全局关闭。

本次 S0 是可迭代的离线治理基线，不代表所有未来能力已实现。工程验收记录与用户对具体 3D 资产的批准相互独立。
