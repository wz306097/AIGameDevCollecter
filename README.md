# AIGameDevCollecter

AIGameDevCollecter 是一个面向 Godot AI 游戏开发流程的被动采集器。它不会改变你的开发方式，而是从目标游戏仓库的 git 历史、验证结果和 AI agent transcript 中整理真实开发会话，自动标记 bad case，并把 bad case 导出给 AIGameDevBench 作为可运行的回归 testcase。

CLI 名称是 `survey`。

## 能解决什么

- 在普通 Godot 仓库里持续记录 AI 开发 session。
- 基于 L0/L1 验证、人工介入比例、修复轮次等信号自动发现 bad case。
- 自动关联 Claude Code / Codex transcript，补齐 AI agent 的输入、输出、工具调用和 token 信息。
- 手动上报 bad case 时，也自动合并匹配的 transcript 上下文。
- 同时导出两类 AIGameDevBench 资产：
  - `survey_bad_cases.json`：给 Bench Reports 页面展示。
  - `testcases/survey-*`：给 Bench 像普通 testcase 一样 `list/run`。

## 安装

```powershell
cd C:\Users\WinterZhao\Codes\AIGameDevCollecter
python -m pip install -e ".[dev]"
```

要求 Python 3.10+。基础依赖只有 `click`，Python 3.10 下额外需要 `tomli`。Godot L0 场景加载检查是可选能力：如果 PATH 里没有 `godot`，纯语法和静态检查仍可运行；如果需要指定 Godot，可在 Bench 侧用 `--godot-binary`。

## 快速开始

在要观察的 Godot 游戏仓库里运行：

```powershell
cd C:\Users\WinterZhao\Codes\godot_demo
survey watch --once
```

`watch` 会自动创建 `survey` 存储分支、安装 post-commit hook、扫描最近 git 历史、计算 metrics，并把新发现的 bad case 写入 `survey` 分支。持续观察时去掉 `--once`：

```powershell
survey watch --interval 30m
```

常用时间格式：

```powershell
survey watch --interval 45s
survey watch --interval 30m
survey watch --interval 2h
```

## bad case 何时触发

当前内置规则在 `survey.badcase.detect_bad_case` 中：

| 信号 | 触发条件 | 常见分类 |
|---|---|---|
| L0 失败 | GDScript 基础语法错误、场景加载失败等 | `A1` |
| L1 失败 | 场景资源引用、signal target 等结构完整性失败 | `A1` / `A2` |
| 人工介入过高 | `human_intervention_ratio > 0.4` | `C1` |
| 修复轮次过多 | `rounds_to_resolution > 4` | 低置信度 bad case |
| 用户纠正语气 | transcript 中出现 “wrong / not what I wanted / 错了 / 不是”等纠正信号 | `B1` |

自动发现的 bad case 会先带 `suggested_type`。你可以用下面的命令查看待确认项：

```powershell
survey tag --pending
```

确认或手动上报：

```powershell
survey tag --last --type B1 --notes "Timer signal mismatch"
survey tag unknown_2026-06-25_000 --type C1 --notes "human_intervention_ratio=1.00"
```

默认情况下，`tag` 会尝试自动找到并合并匹配的 Claude Code / Codex transcript。确实不需要上下文时才使用：

```powershell
survey tag --last --type B1 --no-transcript
```

## transcript 自动关联

Survey 支持两类 transcript：

| harness | 默认发现位置 | 匹配方式 |
|---|---|---|
| Claude Code | `~/.claude/projects/<repo-path>/` | 文件路径重叠 |
| Codex | `~/.codex/sessions/**/*.jsonl` | 先按 transcript metadata 的 `cwd` / `workspace_roots` 过滤当前 repo，再按 commit 或文件重叠合并 |

导入当前 repo 的 transcript：

```powershell
survey import-transcripts
```

只导入 Codex：

```powershell
survey import-transcripts --harness codex
```

指定 transcript 文件或目录：

```powershell
survey import-transcripts --harness codex --path C:\path\to\session.jsonl
survey import-transcripts --harness claude-code --path C:\path\to\claude-project-dir
```

导入后，匹配到 bad case 的 transcript 会写入 session：

- `prompts[*].user_message`：agent 输入
- `prompts[*].assistant_summary`：agent 输出摘要
- `prompts[*].tool_calls`：工具调用与关联文件
- `system_context.transcript_path`
- `system_context.codex_session_id`
- `system_context.total_tokens`
- `system_context.transcript_filtered_turns`
- `system_context.transcript_filtered_to_commits`

## 导出给 AIGameDevBench

从被观察的游戏仓库里执行：

```powershell
cd C:\Users\WinterZhao\Codes\godot_demo

survey export-bench `
  --output ..\AIGameDevBench\survey_bad_cases.json `
  --testcases-dir ..\AIGameDevBench\testcases `
  --harness survey-godot-demo
```

这一步默认会先自动导入当前 repo 的 Claude Code / Codex transcript。需要禁用时：

```powershell
survey export-bench `
  --output ..\AIGameDevBench\survey_bad_cases.json `
  --testcases-dir ..\AIGameDevBench\testcases `
  --harness survey-godot-demo `
  --no-transcript
```

持续刷新 Bench 输出：

```powershell
survey watch `
  --bench-report ..\AIGameDevBench\survey_bad_cases.json `
  --bench-testcases-dir ..\AIGameDevBench\testcases `
  --bench-harness survey-godot-demo
```

导入 transcript 后立即刷新 Bench：

```powershell
survey import-transcripts `
  --bench-report ..\AIGameDevBench\survey_bad_cases.json `
  --bench-testcases-dir ..\AIGameDevBench\testcases `
  --bench-harness survey-godot-demo
```

手动上报并刷新 Bench：

```powershell
survey tag --last --type B1 --notes "Timer signal mismatch" `
  --bench-report ..\AIGameDevBench\survey_bad_cases.json `
  --bench-testcases-dir ..\AIGameDevBench\testcases `
  --bench-harness survey-godot-demo
```

## Bench 侧怎么使用

进入 AIGameDevBench：

```powershell
cd C:\Users\WinterZhao\Codes\AIGameDevBench
```

查看 Reports 页面：

```powershell
aigdbench serve --reports-dir .
```

列出 Survey 生成的 testcase：

```powershell
aigdbench list --testcases-dir testcases
```

运行一个 Survey bad case：

```powershell
aigdbench run `
  --testcases-dir testcases `
  --testcase survey-unknown_2026-06-25_000 `
  --driver command `
  --harness codex `
  --harness-cmd "codex exec --cd {workspace} {task}" `
  --timeout 600 `
  --godot-binary D:\Godot\godot\bin\godot.windows.editor.x86_64.console.exe
```

Survey 生成的 `testcases/survey-*` 是标准 Bench testcase 目录：

```text
testcases/survey-unknown_2026-06-25_000/
  testcase.toml          # Bench manifest
  survey_bad_case.json   # bad case、agent context、原 session、期望信号
  bad.diff               # 原 bad commit diff，用于防止原样复现
```

Bench 的 `survey_bad_case` verifier 会检查：

- 新 harness 必须改动原 bad case 相关的真实源文件。
- 新 diff 不能与 `bad.diff` 完全一致。
- L0/L1 gate 必须通过。
- 对人工介入/多轮 bad case，`ai_agent_context.turns` 必须存在。
- `.uid`、`.import`、`.godot/` 等 Godot 生成物不会被算作有效相关改动。

## 数据流

```text
game repo git history
  -> GitDiffAdapter groups commits into Survey sessions
  -> metrics computes AI/human lines, rounds, tokens, duration
  -> validation runs L0/L1 checks
  -> badcase detects or suggests bad-case tags
  -> transcripts merge Claude Code / Codex agent context
  -> survey branch stores sessions/*.json
  -> export-bench writes:
       - AIGameDevBench/survey_bad_cases.json
       - AIGameDevBench/testcases/survey-*
```

## 存储模型

Survey 不会把采集数据写进当前工作树。它使用一个独立的 orphan 分支：

```text
survey
  survey.toml
  sessions/*.json
  transcripts/.gitkeep
  reports/.gitkeep
```

查看配置：

```powershell
survey config show
```

导出当前 sessions JSON：

```powershell
survey report --format json
```

生成 Markdown 汇总：

```powershell
survey report --period 30d
```

## 代码结构

```text
src/survey/
  cli.py                 # Click 命令入口，只做参数解析和用户输出
  storage.py             # survey 分支自动初始化
  transcripts.py         # Claude Code / Codex transcript 自动发现、导入、合并
  bench_testcases.py     # Bench report 和 runnable testcase 导出
  report.py              # Survey summary 和 Bench JSON report 结构
  badcase.py             # bad case 检测与建议分类
  metrics.py             # outcome metrics
  inference.py           # session / transcript 关联
  branch.py              # survey orphan branch 读写
  adapters/
    git_diff.py          # 从 git history 推断 session
    claude_code.py       # Claude Code transcript parser
    codex.py             # Codex jsonl transcript parser
```

## 命令速查

| 命令 | 作用 |
|---|---|
| `survey init [--name N]` | 创建 survey 分支并安装 hook |
| `survey collect [--since 7d]` | 从 git history 做一次采集 |
| `survey watch [--interval 30m] [--once]` | 周期采集并自动标记 bad case |
| `survey verify [--last]` | 对 session 跑 L0/L1 |
| `survey tag --pending` | 列出待确认 bad case |
| `survey tag <id> --type B1` | 手动确认/上报 bad case，并默认合并 transcript |
| `survey import-transcripts` | 自动导入 Claude Code / Codex transcript |
| `survey export-bench --output ... --testcases-dir ...` | 导出 Bench report 和 runnable testcase |
| `survey report [--format md\|json]` | 生成 Survey 汇总 |
| `survey config show` | 查看合并后的配置 |

## 测试

```powershell
python -m pytest
```

常用局部测试：

```powershell
python -m pytest tests\test_cli.py tests\test_report.py
python -m pytest tests\test_codex_adapter.py tests\test_claude_code_adapter.py
```
