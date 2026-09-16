# endfield_valley_v1 — 用户输入的风格包

这是从 81 张终末地环境截图整理的参数提案，可通过通用用户 style 入口检查和准备。
原始提案保留 `unreviewed`，且未附带 `materials/library.blend` 与
`calibration/calibration.blend`，因此**尚不能直接用于场景生产**。

`profile.yaml` 是入口。`format_version: '1.0'` 表示运行时支持的数据格式；
`version: 1.1.0` 是本包的发布版本。用户发布新的兼容包版本，无需修改运行时代码的版本白名单。
本目录就是包根目录。

## 检查与使用

在 two-stage-3d 根目录及已有的专用 Python 环境执行：

```text
python -m runtime.cli style-inspect styles/endfield_valley_v1/versions/1.1.0
python -m runtime.cli style-prepare styles/endfield_valley_v1/versions/1.1.0 --output .deps/endfield-style-candidate
```

第二条命令要求尚不存在、位于源包之外的输出目录。它复制声明的数据文件并生成 MCP 校准请求；
它本身不执行 Blender、不代签评审。按返回的 `execute_code` 通过 MCP 执行后，
检查真实校准图、资源名称和来源范围。真实设计评审完成后，才在候选包中记录评审者及
`review_status: design_reviewed`。这些字段属于设计评审，**不等于用户的视觉方向、几何或最终美术批准**。

若 MCP 安全模式拒绝加载本地校准脚本，候选只停留在准备状态，需由用户调整插件权限后重试。
本次已连接 Blender 5.2.1，但遇到此限制，尚未产生本包的真实校准资源或视觉验收结论。

完整包通过检查后，在已初始化且尚未批准视觉方向的项目中导入：

```text
python -m runtime.cli style-import PROJECT PACKAGE --expected-version N
python -m runtime.cli style-resolve --project PROJECT --profile endfield_valley_v1 --version 1.1.0 --material painted_metal --condition clean
```

将 `PROJECT`、`PACKAGE`、`N` 替换为项目路径、完整候选包路径和当前项目版本。
导入自动使用 `PROJECT/styles/endfield_valley_v1/versions/1.1.0`，保存文件哈希并禁止覆盖。
Stage 0 的 `style_assignment` 显式选择本包 ID 和版本；导入不会自动改变已选风格或批准场景。

## 文件与校验范围

- `materials/definitions.yaml`：七类材质与三种表面状态。
- `style_signature.yaml`：十一维风格参数、设计评审状态和证据范围。
- `lighting/overcast.yaml`、`atmosphere/default.yaml`、`camera/environment.yaml`、`color/default.yaml`、`render/preview.yaml`：环境及预览参数。
- `critic/rubric.yaml`：用于实际图像评审的九项主观标准。
- `provenance.json`：配色绑定和证据限制，随导入、操作包保护和交付保留。

校准必须导出名为 `endfield_valley_v1.<材质类别>` 的材质。
直接复制 `industrial_acg_v1` 的 BLEND 文件不能保证这些名称存在；应根据本包参数生成自己的库。
`style-inspect` 只验证定义、评审字段及资源文件头，不能证明 Blender 已打开文件或视觉质量已达标。

签名计算已复现：painted_metal 的 RGB 为 `0.3373 / 0.3882 / 0.3882`，bump 为 `0.0067648`，
roughness 为 `0.3802`；emissive strength 为 `2.42`；key/fill energy 为 `2537.55 / 587.18`；
fog density 为 `0.0055376`。这些是参数结果，不是渲染或美术验收证据。

## 证据边界

- 源索引中 81 张图均为 `license=unknown`、`license_verified=false`。保留其仅作风格观察、不得再分发的使用限制；本包不附带截图。
- rubber 只有一帧履带/轮胎证据；色表经人工绑定，仍需真实视觉评审。
- 原始提案没有程序化校准样本或渲染原型，其 `evidence_scope` 保留这一事实。
- 材质定义中除 base_color 外的数值继承 `industrial_acg_v1` 1.1.0，随后由签名有界缩放。
- `analysis/out/style_proposal.yaml` 等分析文件在原始分析工程中，不是包内的执行依赖。

通用输入约定见[用户 style 指南](../../../../docs/v02/user-styles.md)。
