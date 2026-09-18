# 用户提供 style

Style 可以来自用户给出的参数包，也可以由 Codex 根据用户的文字、参考图和现有模板整理。
文字和图片的解释属于 Agent；运行时接收明确数据，不自动给截图分类或推断美术批准。
用户包是项目输入，不需要修改 Skill 源码或放入共享的内置 styles 目录。

## 入口和状态

`style-inspect PACKAGE` 接收直接包含 `profile.yaml` 的目录。它完整检查定义，即使签名尚未评审，
也能报告 `pending` 及缺少的 `design_review`、`library`、`calibration`。
`validated` 只表示定义、声明的评审字段及 BLEND 文件头通过检查，不证明内部材质名称、渲染或美术质量。
非法定义返回明确错误，不切换到内置风格。

`style-prepare PACKAGE --output NEW_DIRECTORY` 创建独立候选目录，复制声明的数据与来源记录，
生成带输入哈希的 MCP 校准请求。它不复制旧材质库、不覆盖现有目录，也不修改源包或评审字段。
通过 Blender MCP 执行返回的 `execute_code`，等待真实结果，再检查 `preview.png` 和
`calibration-result.json`。请求会检查输入摘要、最低 Blender 版本和七个规范材质名称，并恢复原活动场景。
失败或部分输出不能冒充完成；重试先检查已有结果，需要重做时准备新目录。

MCP 必须允许执行本项目的本地 worker。若插件安全模式禁止 `runpy`、文件读取或库加载，
保留 `prepared` 状态并报告具体拒绝原因，等待用户调整插件权限；不得绕过限制、改走 batch，
也不得补造校准回执。能连接 MCP 不等于它允许执行校准请求。

设计评审者检查用户意图、实际参考证据和校准图之后，才在候选签名中记录自己的
`reviewed_by` 和 `review_status: design_reviewed`。用户作者、人工评审者与 Codex 均可具名评审；
未评审输入保持 `unreviewed`。运行时无法验证一句评审声明的真实性，Agent 不应代造依据。
这不是项目中的用户批准，Stage 0、几何和最终评审仍分别执行。

## 包格式 1.0

`contracts/style_package.schema.json` 定义 profile。`format_version: '1.0'` 是格式能力，
`version: X.Y.Z` 是用户独立发布的版本。ID 为 1–64 个字母、数字、下划线或短横线，首字符为字母或数字。
版本必须显式选择，不寻找“最新”版本。旧内置 1.0.0/1.1.0 文件保持兼容。

profile 使用包内相对路径声明八个组件 materials、lighting、atmosphere、camera、color、render、signature、critic，
两个资源 library、calibration，以及 provenance。禁止路径逃逸、链接、重复文件声明和重复 YAML 字段。
只读取 JSON/YAML 数据，不展开环境变量、不运行包内代码，也不递归复制无关文件。

材质能力沿用七类 `painted_metal`、`bare_metal`、`concrete`、`rubber`、`glass`、`emissive`、`vegetation`，
状态为 `clean`、`lightly_weathered`、`weathered`。十一维签名保持已有数值边界及几何保留约束。
灯光 profile 名可由用户命名，其实现仍是世界光和两盏区域灯。渲染仍为 Cycles / AgX。
输入新风格不意味着自动支持任意新着色器、HDRI、材质类别或几何生成算法。

`evidence_scope` 是非空的具名文本映射，无需沿用内置示例的 pump/station 名称。
provenance 至少包含相符的 `style_id`、`version` 和非空 `evidence_limits` 文本数组；可附加配色绑定等来源数据。
保留 unknown/unverified 许可事实，不将输入包当作外部图片再分发许可。
critic 须声明相符的 `profile_version`、分数的主观含义和现有九项评审类别。
材料库须包含 `<style_id>.<material_class>`；跨包复制文件名不会改写内部材质名称。

参考结构见 `styles/endfield_valley_v1/versions/1.1.0` 用户草案；它保留待评审和缺少资源的事实。

## 导入、选择和交付

先初始化视觉项目或读取现有状态，再执行：

```text
python -m runtime.cli style-import PROJECT PACKAGE --expected-version N
python -m runtime.cli style-resolve --project PROJECT --profile STYLE_ID --version X.Y.Z --material painted_metal --condition clean
```

只有完整、设计评审已声明的包可导入。ManifestManager 在锁下校验版本和状态，
把原字节和 `package-lock.json` 一次性写入 `PROJECT/styles/STYLE_ID/versions/X.Y.Z`，
增加项目版本但不改变场景状态或创建批准。仅允许视觉方向批准前导入；已有同版本不可覆盖。
调整导入包时发布新版本，并在支持的规划阶段重新选择，不要原地改文件。

Stage 0 `style_assignment` 显式填写 `style_profile`、`profile_version` 和包内环境 profile 名。
项目同 ID/版本的显式导入优先于内置资源；存在但损坏的导入必须拒绝，不能回退。
没有导入或没有选择新包时，既有 `industrial_acg_v1` 1.0.0 默认不变。

Stage 1 材质解析、Stage 2 操作包、Stage 3 rubric 和最终交付都使用项目内副本。
声明的 profile、组件、BLEND、provenance 和导入清单进入摘要保护及交付。
删除原始目录或迁移项目后仍可解析；迁移机器后重新生成含绝对路径的操作包。

## 本次验证范围（2026-09-16）

真实 CLI 已检查终末地草案、准备独立候选，并验证缺少评审的草案不能导入。
另以现有工业风格的真实 BLEND 文件组成格式 1.0 输入，完成项目导入、移走来源目录和
迁移项目后的解析；这证明真实文件传输与解析，不证明终末地材质已经生成。
自动化覆盖项目选择、场景操作包、评审和交付，涉及渲染回执的流程使用明确的测试替身。

本机已通过 MCP 连接 Blender 5.2.1 LTS；插件安全模式在执行前拒绝了校准调度。
终末地候选的真实材质库、校准场景、预览图及回执均未生成，真实渲染与视觉匹配保持
`unresolved`，原始签名仍为 `unreviewed`。没有新增用户美术批准。
工作副本的 `.deps/user-style-input/` 保存首次失败、真实 CLI 与连接检查记录；
正式治理状态以工具生成的 `changes/` 记录为准。
