# Meeting Summary / 会议总结工具

> A Claude Code skill that automatically converts video meeting recordings into structured Markdown summary reports.
>
> 一个 Claude Code Skill，将视频会议录屏自动转化为结构化 Markdown 会议总结报告。

---

## Features / 功能特性

| English | 中文 |
|---------|------|
| Automatic keyframe extraction via PySceneDetect | 使用 PySceneDetect 自动提取关键帧截图 |
| Audio transcription via OpenAI Whisper | 使用 OpenAI Whisper 转录音频 |
| External subtitle file support (SRT/VTT/JSON/TXT) | 支持外部字幕文件（SRT/VTT/JSON/TXT） |
| Structured JSON output for AI analysis | 输出结构化 JSON 供 AI 分析 |
| Auto-generated Markdown meeting report | 自动生成 Markdown 会议总结报告 |
| Auto-installation of missing dependencies | 缺失依赖自动安装 |

---

## Architecture / 架构概览

```
User Input / 用户输入 (video + optional subtitles / 视频 + 可选字幕)
       │
       ▼
  Python Script / Python 脚本 (meeting_processor.py)
  ├─ Keyframe Extraction / 关键帧提取 (PySceneDetect)
  ├─ Audio Transcription / 音频转录 (Whisper) 
  │  OR Subtitle Parsing / 字幕解析 (SRT/VTT/JSON/TXT)
  └─ Output / 输出: meeting_data.json + screenshots/
       │
       ▼
  Claude Code AI Analysis / Claude Code AI 分析
  ├─ Read structured data / 读取结构化数据
  ├─ View keyframe screenshots / 查看关键帧截图
  └─ Generate Markdown report / 生成 Markdown 报告
```

---

## Project Structure / 项目结构

```
meeting-summary/
└── .claude/
    └── skills/
        └── meeting-summary/
            ├── SKILL.md                        # Skill workflow definition / Skill 工作流定义
            ├── scripts/
            │   └── meeting_processor.py        # Core video processing script / 核心视频处理脚本
            ├── references/
            │   └── meeting-report-template.md  # Report output template / 报告输出模板
            └── .venv/                          # Python virtual environment (runtime) / Python 虚拟环境（运行时）
```

---

## Prerequisites / 前置要求

### System Tools / 系统工具

| Tool | Install (macOS) | Install (Ubuntu) |
|------|----------------|-----------------|
| Python 3.8+ | `brew install python` | `sudo apt install python3` |
| ffmpeg | `brew install ffmpeg` | `sudo apt install ffmpeg` |

> **Note / 注意**: `ffmpeg` will be auto-installed via Homebrew on macOS if missing.  
> `ffmpeg` 在 macOS 上缺失时会自动通过 Homebrew 安装。

### Python Dependencies / Python 依赖

Dependencies are **automatically installed** on first run via the virtual environment.  
依赖项会在**首次运行时自动安装**到虚拟环境中。

| Package | Purpose / 用途 |
|---------|---------------|
| `scenedetect[opencv]` | Video scene detection / 视频场景检测 |
| `openai-whisper` | Audio speech-to-text / 音频语音转文字 |
| `tqdm` | Progress display / 进度条显示 |

---

## Usage / 使用方式

### Via Claude Code Skill (Recommended) / 通过 Claude Code Skill（推荐）

Simply tell Claude Code to summarize your meeting:

直接告诉 Claude Code 进行会议总结：

```
# English triggers:
"meeting summary for /path/to/meeting.mp4"
"summarize meeting from recording.mp4"

# 中文触发词:
"会议总结 /path/to/meeting.mp4"
"总结会议录屏 recording.mp4"
"帮我总结这个会议视频"
```

Claude Code will guide you through the full workflow automatically.  
Claude Code 会自动引导你完成完整的处理流程。

### Direct Script Execution / 直接执行脚本

```bash
# Set virtual environment Python / 设置虚拟环境 Python
VENV_PYTHON=~/.claude/skills/meeting-summary/.venv/bin/python

# Basic usage - audio auto-transcription / 基础用法（自动转录音频）
$VENV_PYTHON ~/.claude/skills/meeting-summary/scripts/meeting_processor.py \
  --video meeting.mp4 \
  --output ./output/my-meeting

# With external subtitle file / 使用外部字幕文件
$VENV_PYTHON ~/.claude/skills/meeting-summary/scripts/meeting_processor.py \
  --video meeting.mp4 \
  --subtitle meeting.srt \
  --skip-transcription \
  --output ./output/my-meeting

# Skip keyframe extraction / 跳过关键帧提取
$VENV_PYTHON ~/.claude/skills/meeting-summary/scripts/meeting_processor.py \
  --video meeting.mp4 \
  --skip-keyframes \
  --subtitle meeting.vtt
```

### CLI Parameters / 命令行参数

| Parameter / 参数 | Default / 默认值 | Description / 说明 |
|-----------------|-----------------|-------------------|
| `--video` | *(required)* | Video file path / 视频文件路径 |
| `--subtitle` | — | External subtitle file / 外部字幕文件 |
| `--output` | `./meeting_output` | Output directory / 输出目录 |
| `--whisper-model` | `base` | Whisper model size: `tiny/base/small/medium/large` |
| `--language` | `zh` | Transcription language / 转录语言代码 |
| `--adaptive-threshold` | `3.5` | Scene detection sensitivity / 场景检测灵敏度（越大越不灵敏） |
| `--min-scene-len` | `3.0` | Minimum scene length in seconds / 最短场景秒数 |
| `--downscale` | `2` | Video downscale factor / 视频降采样倍数 |
| `--skip-keyframes` | `false` | Skip keyframe extraction / 跳过关键帧提取 |
| `--skip-transcription` | `false` | Skip Whisper transcription / 跳过 Whisper 转录 |

---

## Supported Subtitle Formats / 支持的字幕格式

| Format | Extension | Source / 来源示例 |
|--------|-----------|-----------------|
| SRT | `.srt` | Tencent Meeting, Zoom, Feishu / 腾讯会议、Zoom、飞书导出 |
| WebVTT | `.vtt` | Browser recordings, YouTube / 浏览器录制、YouTube 字幕 |
| Whisper JSON | `.json` | Output from a previous run / 本工具上次运行的输出 |
| Timestamped TXT | `.txt` | `[12.3s] text` format |
| Plain text | `.txt` | Manually prepared transcripts / 手动整理的转录 |

---

## Output Files / 输出文件

After processing, the output directory contains:  
处理完成后，输出目录包含以下文件：

```
<output_dir>/
├── meeting_data.json      # Structured scene data / 结构化场景数据
├── meeting_summary.md     # AI-generated report / AI 生成的会议总结报告
├── transcript.json        # Whisper transcription segments / Whisper 转录片段（Whisper 模式）
├── transcript.txt         # Human-readable transcript / 可读转录文本（Whisper 模式）
├── audio.wav              # Extracted audio / 提取的音频（Whisper 模式）
└── screenshots/           # Keyframe screenshots / 关键帧截图
    ├── 00m00s-00m25s.jpg
    ├── 00m25s-05m20s.jpg
    └── ...
```

### meeting_data.json Structure / 数据结构

```json
{
  "metadata": {
    "video_path": "meeting.mp4",
    "duration_sec": 3600.0,
    "total_scenes": 42,
    "language": "zh",
    "transcription_source": "srt",
    "processing_time_sec": 12.5
  },
  "scenes": [
    {
      "index": 1,
      "start_sec": 0.0,
      "end_sec": 25.3,
      "start_time": "00:00:00",
      "end_time": "00:00:25",
      "screenshot_path": "screenshots/00m00s-00m25s.jpg",
      "transcript": "会议开始，主持人介绍今天的议程..."
    }
  ],
  "full_transcript": "..."
}
```

---

## Report Template / 报告模板

The generated `meeting_summary.md` follows a structured template:  
生成的 `meeting_summary.md` 遵循以下结构化模板：

- 🎯 **Meeting Overview / 会议概述** — 2-3 sentence summary
- 📌 **Topics & Conclusions / 议题与结论** — Chronological agenda items with screenshots
- ✅ **Action Items / 行动项** — Assignee, deadline, priority table
- 🤝 **Decision Log / 决策记录** — Decisions and rationale
- ❓ **Pending Items / 待议事项** — Unresolved discussions
- 👥 **Speaker Summaries / 参会者发言摘要** — Per-person or per-role summaries

---

## Troubleshooting / 故障排除

| Issue / 问题 | Solution / 解决方案 |
|-------------|-------------------|
| Too many scenes detected (>100) / 场景过多 | Increase `--adaptive-threshold` (e.g., 5.0) / 提高阈值 |
| Too few scenes detected (<5) / 场景过少 | Decrease `--adaptive-threshold` (e.g., 2.0) / 降低阈值 |
| Whisper transcription failed / Whisper 转录失败 | Provide an external subtitle file with `--subtitle` / 改用 `--subtitle` |
| Empty subtitle parsing / 字幕解析为空 | Check file encoding (UTF-8) and format / 检查文件编码和格式 |
| Script timeout / 脚本超时 | Increase `--downscale` or use smaller Whisper model (e.g., `tiny`) |
| ffmpeg not found / 未找到 ffmpeg | Run `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` |

---

## Virtual Environment Notes / 虚拟环境说明

- **Location / 固定位置**: `~/.claude/skills/meeting-summary/.venv`
- Created automatically on first run / 首次运行时自动创建
- Reused on subsequent runs / 后续运行直接复用，不重复安装
- ⚠️ **Do NOT commit to version control** / 禁止纳入版本控制
- ⚠️ **Not cross-platform portable** / 不可跨平台移植

---

## License / 许可证

This project is intended for internal use as a Claude Code skill.  
本项目作为 Claude Code Skill 供内部使用。
