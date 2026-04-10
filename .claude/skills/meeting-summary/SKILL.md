---
name: meeting-summary
description: >
  Use when the user wants to summarize a meeting from a video recording
  or transcript/subtitle file. Triggers on: "会议总结", "meeting summary",
  "总结会议", "summarize meeting", or when user provides a meeting video
  with subtitle files (.srt, .vtt).
---

# 会议总结 Skill

将视频会议录屏自动转化为结构化 Markdown 会议总结报告。

## 架构概览

```
用户输入 (视频 + 可选字幕)
       │
       ▼
  Python 脚本处理 (meeting_processor.py)
  ├─ 关键帧提取 (PySceneDetect)
  ├─ 音频转录 (Whisper) 或 字幕解析 (SRT/VTT)
  └─ 输出 meeting_data.json + screenshots/
       │
       ▼
  Claude Code AI 分析
  ├─ 读取结构化数据 + 查看截图
  └─ 生成 Markdown 报告
```

## 工作流程

严格按以下 4 个阶段顺序执行：

### 阶段 1: 收集输入

1. **确认视频文件**：向用户确认视频文件路径，验证文件存在
2. **确认字幕文件**（可选）：询问是否有外部字幕文件（SRT/VTT），如有则确认路径
3. **确认输出目录**：默认 `./meeting_output/<YYYY-MM-DD-HHmmss>_<topic>`，允许用户自定义
4. **依赖环境**：脚本必须在虚拟环境中运行（避免系统 Python 的 externally-managed-environment 限制）。
   虚拟环境固定位置：`~/.claude/skills/meeting-summary/.venv`，首次运行时自动创建，后续复用。
   ⚠️ `.venv` 是运行时产物，不可跨平台移植，禁止纳入版本控制或 skill 分发包。

### 阶段 2: 执行处理脚本

**虚拟环境策略**（⚠️ 严格遵守）：

1. **定义 VENV_PYTHON 变量**（跨平台兼容）：
   ```bash
   # macOS/Linux
   VENV_PYTHON=~/.claude/skills/meeting-summary/.venv/bin/python
   # Windows (PowerShell/cmd)
   # VENV_PYTHON=~/.claude/skills/meeting-summary/.venv/Scripts/python.exe
   ```
   根据当前操作系统选择正确的路径。

2. **检查 venv 是否存在**：检查上述 VENV_PYTHON 路径是否存在
3. **如果不存在**：创建虚拟环境（仅此一次）
   ```bash
   python3 -m venv ~/.claude/skills/meeting-summary/.venv
   ```
4. **如果已存在**：直接使用，**禁止**再次运行 `pip install`
5. 始终使用 venv 中的 python 执行脚本（脚本内置 `check_dependencies()` 会在缺包时自动安装）

执行命令：

```bash
$VENV_PYTHON ~/.claude/skills/meeting-summary/scripts/meeting_processor.py \
  --video "<视频路径>" \
  --output "<输出目录>" \
  [--subtitle "<字幕路径>"] \
  [--whisper-model base] \
  [--language zh]
```

**参数决策逻辑**：
- 用户提供了字幕文件 → 加 `--subtitle <path> --skip-transcription`
- 用户未提供字幕 → 不加 `--subtitle`，Whisper 自动转录
- 中英混合会议 → `--language zh`（Whisper 对中文优化较好，能自动处理夹杂的英文）

**等待脚本完成**：脚本可能运行较长时间（取决于视频时长和 Whisper 模型），在执行过程中向用户说明进度。

### 阶段 3: AI 分析

脚本完成后，按以下步骤进行分析：

1. **读取结构化数据**：使用 Read 工具读取 `<输出目录>/meeting_data.json`
2. **查看关键帧截图**：使用 Read 工具查看 `<输出目录>/screenshots/` 下的截图文件（Claude Code 支持多模态，直接读取图片即可分析）
3. **分析会议内容**：基于以下分析框架进行分析

#### 分析框架

你是一位专业的会议记录分析师，正在分析一次视频会议的录屏。你会收到：
- 按时间顺序排列的场景数据（时间戳 + 转录文本）
- 对应时间点的屏幕截图

请执行以下分析任务：

**1. 识别会议议题**
- 根据讨论内容的主题转换识别不同议题
- 每个议题提炼标题、讨论要点和结论
- 关注截图中展示的内容（PPT、文档、代码、设计稿等），将其与讨论内容关联

**2. 提取 Action Items**
- 捕捉所有明确或隐含的待办事项
- 关键词："需要"、"必须"、"下一步"、"谁来负责"、"截止"、"deadline"
- 尽量提取负责人、截止日期和优先级

**3. 记录决策**
- 识别会议中达成的共识和明确决定
- 记录决策的理由和上下文

**4. 标记待议事项**
- 识别有争议、未达成共识的话题
- 标注分歧点和各方立场

**5. 参会者发言摘要**
- 如能通过称呼、语气变化识别不同参会者，按人分组总结
- 如无法明确区分，按角色（主持人、汇报人等）分组
- 提炼每人的核心观点和代表性发言

**语言处理**：
- 输出统一使用中文
- 保留英文技术术语原词（如 API、Sprint、Figma、UI/UX）
- 中英混合内容正确处理，不遗漏英文部分的语义

### 阶段 4: 生成报告

参照 `references/meeting-report-template.md` 中的模板格式，生成完整的 Markdown 报告。

**报告保存**：
```
<输出目录>/meeting_summary.md
```

**报告生成规则**：
1. 使用模板中定义的章节结构和格式
2. 所有章节必须填充（无内容的章节标注"本次会议未涉及此项"）
3. 时间引用使用 `HH:MM:SS` 格式
4. **截图嵌入**：在每个议题的「相关截图」处，使用 Markdown 图片语法嵌入对应截图，路径使用相对路径。截图文件名格式为时间戳: `00m25s-05m20s.jpg`。示例：
   ```markdown
   **相关截图**:
   ![00m25s-05m20s](screenshots/00m25s-05m20s.jpg)
   ```
   根据 `meeting_data.json` 中每个 scene 的 `screenshot_path` 字段获取实际文件名。每个议题至少嵌入一张最相关的截图；如果议题跨越多个场景，可嵌入多张。
5. 报告末尾附上输出目录中所有文件的清单

**完成后**：
- 向用户展示报告的关键摘要（概述 + Action Items 数量）
- 告知报告保存路径
- 询问是否需要对某个议题展开更详细的分析

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| 视频文件不存在 | 提示用户检查路径，要求重新提供 |
| ffmpeg 未安装 | 提供安装命令 (brew/apt) |
| Python 依赖缺失 | 提供 pip install 命令 |
| Whisper 转录失败 | 建议用户提供外部字幕文件替代 |
| 场景数量过多 (>100) | 建议提高 `--adaptive-threshold` (3.5→5.0) |
| 场景数量过少 (<5) | 建议降低 `--adaptive-threshold` (3.5→2.0) |
| 字幕解析为空 | 检查文件格式，提示支持的格式列表 |
| 脚本执行超时 | 建议增大 `--downscale` 或使用更小的 Whisper 模型 |

## 支持的字幕格式

| 格式 | 扩展名 | 来源示例 |
|------|--------|---------|
| SRT | `.srt` | 腾讯会议、Zoom、飞书导出 |
| WebVTT | `.vtt` | 浏览器录制、YouTube 字幕 |
| Whisper JSON | `.json` | 本工具上次运行的输出 |
| 时间戳 TXT | `.txt` | `[12.3s] 文本` 格式 |
| 纯文本 | `.txt` | 手动整理的转录 |
