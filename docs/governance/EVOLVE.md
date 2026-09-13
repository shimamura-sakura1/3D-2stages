# 如何迭代这个 Skill

生产工作从 SKILL.md 的 Execution Router 进入；修改 Skill 本身时必须严格遵循用户指定的 Contract-Governed Skill 定义，本机路径为 `/Users/tachibanakanade/contract-govern-skil`。先读取该框架 README、spec/SPEC.md、lifecycle/EVOLVE.md 与 lifecycle/TEST_POLICY.md，再使用本项目入口执行；本文不替代外部规范。项目持久要求保存在 AGENTS.md，平台设置见 ../platforms.md。

## 每次改动

1. 阅读 SKILL.md、interface.json、requirements.json、tests/manifest.json 和最新 changes 记录。先区分“新的生成任务”和“修改 Skill 能力”。
2. 给新需求分配新的 REQ ID，把它拆为可验证的 claims。明确它进入哪个 Router Step、由 Agent 判断什么、运行时校验什么、完成后回到哪里。尚无真实证据的能力保持 unresolved。
3. **先写测试并确认失败**。条件能力分别验证启用、原默认路径、缺失/非法输入拒绝；保留已有测试文件和断言。
4. 找出直接受影响的 artifact，运行影响分析。这里的关系方向是“调用者/依赖者 → 被使用者”，downstream 表示受影响的调用方。

```powershell
python scripts/govern.py impact --from runtime.asset_router
python scripts/govern.py impact --from runtime.blender_mcp --from runtime.ssh_transport
```

5. 修改直接相关实现。流程改变才改 SKILL.md；接口/依赖改变同步 interface.json；更新 requirements.json 和 tests/manifest.json。三个测试字段分别维护：covers 是断言，exercises 是实际使用的文件，depends_on_artifacts 是影响分析的依赖。
6. 更新 interface.json 的 skill.version，例如 S0 → S1。生产 manifest 的 schema_version 和 Python 包版本独立管理，不能为治理版本递增而任意改动资产数据格式。
7. 运行以下检查并查看完整报告。先做受影响测试便于调试，验收前仍会执行所有 active 历史测试。

```powershell
python scripts/govern.py validate
python scripts/govern.py test --affected-by runtime.asset_router
python scripts/govern.py contract-test
python scripts/govern.py test --requirement REQ-NEW-ID
python scripts/govern.py accept --requirement REQ-NEW-ID --predicted-impact runtime.asset_router --check
```

8. 审查警告及代表性的真实操作。全部通过后去掉 --check 接受版本；changes 由 skillctl 生成，不手写成功证据。失败时修实现，不能仅为了通过而删除历史断言。

```powershell
python scripts/govern.py accept --requirement REQ-NEW-ID --predicted-impact runtime.asset_router
```

新需求正式替代旧需求时，用 supersedes 显式建立关系并保留旧记录。测试的所有 claims 都被正式替代后，才可将旧测试标为 superseded。不要直接改写已经接受的需求文本和历史测试。

## 当前工具边界

macOS 和 Windows 共用 `python scripts/govern.py`。它通过 `--framework`、进程变量 `CONTRACT_GOVERN_HOME`、本仓库同级 `contract-govern-skil` 顺序定位用户指定框架的本地 checkout，缺失时明确拒绝。默认使用当前启动解释器，也可用 `--python` 指定具备项目和测试依赖的隔离 Python。框架通过临时子进程的 PYTHONPATH 加载，不需要向现有环境安装框架，也不修改框架源码。

治理在源码副本中运行，复制范围由 scripts/govern.py 的 DIRECTORIES/FILES 明确列出。AGENTS.md 及正式源码进入投影；实际 projects、.deps、.skillctl 缓存不进入测试副本和版本快照。新顶层源码目录必须加入该列表；新增普通 runtime、docs、tests 等目录内文件会自动纳入。独占锁及前后摘要用于检测并发修改。完整结果保存在 .skillctl/reports/，成功记录回写 changes/。

跨平台 Git 换行转换导致历史字节摘要不一致时，入口仅在临时副本恢复能精确匹配历史 SHA256 的 LF/CRLF 字节；不会重算历史指纹、改写记录字段或修改原仓库测试。无法通过这两种换行形式恢复的内容改动直接拒绝。恢复清单在报告 `source_projection.restored_newlines`，外部框架继续进行原始哈希和历史回归检查。

不要对包含实际资产的仓库根目录直接运行原始 skillctl accept；它的通用工作副本逻辑不知道本项目的 projects/.deps 边界。使用本项目的治理入口。

## 数据入口

| 文件 | 修改时机 |
| --- | --- |
| SKILL.md | Agent 编排、阶段插入点、返回路径改变 |
| interface.json | 新增公共命令、契约、参考文件或真实依赖 |
| requirements.json | 新需求、可验证断言、显式替代关系 |
| tests/manifest.json | 新测试、覆盖关系、真实执行对象、影响依赖 |
| contracts/ | 真实数据结构改变；同时检查已有项目兼容性 |
| changes/ | 仅由成功的 skillctl accept 写入 |

最初的历史回归登记为一个 95 项测试集合；后续版本另增专项测试，实际数量以当前执行报告为准。影响分析保守地保留整个历史集合。后续可新增更细的专项测试用于快速定位，不能把现有历史集合删掉以缩小验收范围。
