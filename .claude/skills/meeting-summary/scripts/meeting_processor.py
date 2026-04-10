#!/usr/bin/env python3
"""
会议视频处理器
==============
从视频会议录屏中提取关键帧、转录音频或解析字幕文件，
输出结构化的 meeting_data.json 供 Claude Code 分析。

用法:
    python meeting_processor.py --video meeting.mp4
    python meeting_processor.py --video meeting.mp4 --subtitle meeting.srt
    python meeting_processor.py --video meeting.mp4 --skip-keyframes --subtitle meeting.vtt
"""

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─── 依赖检查 ─────────────────────────────────────────────────────────────────

def _install_packages(packages: list[str]):
    """使用 pip 自动安装缺失的 Python 包"""
    print(f"[自动安装] 正在安装: {', '.join(packages)}")
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[错误] pip 安装失败:\n{result.stderr}")
        print(f"  请手动运行: pip install {' '.join(packages)}")
        sys.exit(1)
    print("[自动安装] 安装完成")


def check_dependencies(need_scenedetect: bool = True, need_whisper: bool = True, auto_install: bool = True):
    """检查必要的 Python 包和系统工具是否可用，缺失时自动安装"""
    missing = []

    if need_scenedetect:
        try:
            import scenedetect  # noqa: F401
        except ImportError:
            missing.append("scenedetect[opencv]")

    if need_whisper:
        try:
            import whisper  # noqa: F401
        except ImportError:
            missing.append("openai-whisper")

    try:
        import tqdm  # noqa: F401
    except ImportError:
        missing.append("tqdm")

    if missing:
        if auto_install:
            _install_packages(missing)
        else:
            print(f"[错误] 缺少依赖包: {', '.join(missing)}")
            print(f"  请运行: pip install {' '.join(missing)}")
            sys.exit(1)

    # 检查 ffmpeg，缺失时尝试通过 brew 安装 (macOS)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        if auto_install and sys.platform == "darwin":
            print("[自动安装] 未找到 ffmpeg，正在通过 brew 安装...")
            result = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True, text=True)
            if result.returncode == 0:
                print("[自动安装] ffmpeg 安装完成")
                return
            print(f"[警告] brew install ffmpeg 失败:\n{result.stderr}")
        print("[错误] 未找到 ffmpeg，请手动安装:")
        print("  macOS:   brew install ffmpeg")
        print("  Ubuntu:  sudo apt install ffmpeg")
        print("  Windows: https://ffmpeg.org/download.html")
        sys.exit(1)


# ─── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class Scene:
    """单个场景的数据"""
    index: int
    start_sec: float
    end_sec: float
    image_path: Optional[Path] = None
    transcript: str = ""

    @property
    def start_time(self) -> str:
        """格式化开始时间为 HH:MM:SS"""
        return _format_time(self.start_sec)

    @property
    def end_time(self) -> str:
        """格式化结束时间为 HH:MM:SS"""
        return _format_time(self.end_sec)


def _format_time(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_time_filename(seconds: float) -> str:
    """将秒数格式化为文件名安全的时间格式: 00h05m30s（省略 0h）"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


# ─── 关键帧提取 ────────────────────────────────────────────────────────────────

def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    adaptive_threshold: float = 3.5,
    min_scene_len_sec: float = 3.0,
    downscale: int = 2,
) -> list[Scene]:
    """
    使用 PySceneDetect 的自适应检测器提取视频关键帧。
    每个场景保存中间帧作为截图。
    """
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import AdaptiveDetector
    from scenedetect.scene_manager import save_images

    print(f"\n[1/3] 正在提取关键帧: {video_path.name}")
    output_dir.mkdir(parents=True, exist_ok=True)

    video = open_video(str(video_path))
    fps = video.frame_rate

    manager = SceneManager()
    manager.add_detector(
        AdaptiveDetector(
            adaptive_threshold=adaptive_threshold,
            min_content_val=15.0,
            window_width=2,
        )
    )
    manager.downscale = downscale

    min_scene_frames = int(min_scene_len_sec * fps)
    print(f"  fps={fps:.1f}, downscale=1/{downscale}, "
          f"threshold={adaptive_threshold}, "
          f"min_scene={min_scene_len_sec}s ({min_scene_frames} frames)")

    manager.detect_scenes(video, show_progress=True)
    scene_list = manager.get_scene_list()

    if not scene_list:
        print("  [警告] 未检测到场景切换，请尝试降低 --adaptive-threshold")
        return []

    print(f"  检测到 {len(scene_list)} 个场景")

    # 保存每个场景的中间帧（先用默认编号命名，后续重命名为时间格式）
    save_images(
        scene_list,
        video,
        num_images=1,
        output_dir=str(output_dir),
        image_name_template="scene-$SCENE_NUMBER",
        image_extension="jpg",
        encoder_param=85,
    )

    scenes = []
    for i, (start_tc, end_tc) in enumerate(scene_list, start=1):
        start_sec = start_tc.get_seconds()
        end_sec = end_tc.get_seconds()

        # 将 PySceneDetect 默认文件名重命名为时间格式: 00m00s-00m02s.jpg
        old_path = output_dir / f"scene-{i:03d}.jpg"
        time_name = f"{_format_time_filename(start_sec)}-{_format_time_filename(end_sec)}.jpg"
        new_path = output_dir / time_name

        if old_path.exists():
            old_path.rename(new_path)
            img_path = new_path
        else:
            img_path = None

        scenes.append(Scene(
            index=i,
            start_sec=start_sec,
            end_sec=end_sec,
            image_path=img_path,
        ))

    saved_count = sum(1 for s in scenes if s.image_path)
    print(f"  已保存 {saved_count} 张截图到 {output_dir}/")
    return scenes


# ─── 音频转录 ──────────────────────────────────────────────────────────────────

def transcribe_audio(
    video_path: Path,
    output_dir: Path,
    model_name: str = "base",
    language: str = "zh",
) -> list[dict]:
    """
    使用 ffmpeg 提取音频，再用 Whisper 转录。
    返回 [{start, end, text}] 格式的分段列表。
    """
    import whisper

    print(f"\n[2/3] 正在转录音频 (Whisper model={model_name})")

    audio_path = output_dir / "audio.wav"

    # 提取音频: 16kHz 单声道 16-bit PCM
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [错误] ffmpeg 音频提取失败:\n{result.stderr}")
        return []
    print(f"  音频已提取 → {audio_path.name}")

    # Whisper 转录
    print(f"  正在加载 Whisper '{model_name}' 模型...")
    model = whisper.load_model(model_name)
    print("  正在转录（大文件可能需要较长时间）...")

    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=False,
        verbose=False,
    )

    segments = [
        {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
        }
        for seg in result["segments"]
        if seg["text"].strip()
    ]

    # 保存转录结果
    transcript_json_path = output_dir / "transcript.json"
    transcript_json_path.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    transcript_txt_path = output_dir / "transcript.txt"
    with transcript_txt_path.open("w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"[{seg['start']:.1f}s] {seg['text']}\n")

    print(f"  已转录 {len(segments)} 个片段 → {transcript_json_path.name}")
    return segments


# ─── 字幕文件解析 ──────────────────────────────────────────────────────────────

def parse_srt(content: str) -> list[dict]:
    """
    解析 SRT 字幕格式。
    格式:
        1
        00:00:01,000 --> 00:00:04,000
        字幕文本
    """
    segments = []
    # 按空行分割字幕块
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue

        # 跳过序号行，找时间码行
        time_pattern = re.compile(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
        )

        time_line_idx = -1
        for idx, line in enumerate(lines):
            if time_pattern.search(line):
                time_line_idx = idx
                break

        if time_line_idx < 0:
            continue

        m = time_pattern.search(lines[time_line_idx])
        if not m:
            continue

        # 解析开始和结束时间（秒）
        start_sec = (
            int(m.group(1)) * 3600
            + int(m.group(2)) * 60
            + int(m.group(3))
            + int(m.group(4)) / 1000.0
        )
        end_sec = (
            int(m.group(5)) * 3600
            + int(m.group(6)) * 60
            + int(m.group(7))
            + int(m.group(8)) / 1000.0
        )

        # 时间码之后的所有行都是字幕文本
        text_lines = lines[time_line_idx + 1:]
        text = " ".join(line.strip() for line in text_lines if line.strip())

        # 移除 HTML 标签（某些字幕包含 <i>、<b> 等）
        text = re.sub(r"<[^>]+>", "", text)

        if text:
            segments.append({
                "start": start_sec,
                "end": end_sec,
                "text": text,
            })

    return segments


def parse_vtt(content: str) -> list[dict]:
    """
    解析 WebVTT 字幕格式。
    格式:
        WEBVTT

        00:00:01.000 --> 00:00:04.000
        字幕文本
    """
    # 移除 WEBVTT 头部和可能的元数据
    lines = content.strip().splitlines()
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("WEBVTT"):
            start_idx = i + 1
            break

    # 剩余内容按 SRT 格式解析（VTT 和 SRT 的时间码/文本结构兼容）
    remaining = "\n".join(lines[start_idx:])
    return parse_srt(remaining)


def parse_subtitle(subtitle_path: Path) -> list[dict]:
    """
    根据文件扩展名自动识别并解析字幕文件。
    支持: .srt, .vtt, .json, .txt
    """
    content = subtitle_path.read_text(encoding="utf-8")
    suffix = subtitle_path.suffix.lower()

    if suffix == ".srt":
        print(f"  解析 SRT 字幕: {subtitle_path.name}")
        return parse_srt(content)

    elif suffix == ".vtt":
        print(f"  解析 VTT 字幕: {subtitle_path.name}")
        return parse_vtt(content)

    elif suffix == ".json":
        print(f"  加载 JSON 转录: {subtitle_path.name}")
        data = json.loads(content)
        if isinstance(data, list) and data and "start" in data[0]:
            return data
        print("  [警告] JSON 格式不符合预期，需要 [{start, end, text}] 结构")
        return []

    elif suffix == ".txt":
        print(f"  解析 TXT 文件: {subtitle_path.name}")
        # 尝试带时间戳格式: [12.3s] text
        pattern = re.compile(r"\[(\d+\.?\d*)s\]\s*(.*)")
        segments = []
        for line in content.splitlines():
            m = pattern.match(line.strip())
            if m:
                start = float(m.group(1))
                segments.append({
                    "start": start,
                    "end": start + 30.0,
                    "text": m.group(2),
                })

        if segments:
            # 用下一段的开始时间修正结束时间
            for i in range(len(segments) - 1):
                segments[i]["end"] = segments[i + 1]["start"]
            return segments

        # 纯文本兜底：整体作为单段
        return [{"start": 0.0, "end": 9999.0, "text": content.strip()}]

    else:
        print(f"  [错误] 不支持的字幕格式: {suffix}")
        print("  支持的格式: .srt, .vtt, .json, .txt")
        return []


# ─── 场景-文本对齐 ─────────────────────────────────────────────────────────────

def align_transcript_to_scenes(
    scenes: list[Scene],
    segments: list[dict],
) -> list[Scene]:
    """
    将转录片段按时间窗口分配到对应的场景中。
    使用重叠判定：片段结束 >= 场景开始 AND 片段开始 <= 场景结束。
    """
    print(f"\n[3/3] 正在对齐 {len(segments)} 个转录片段到 {len(scenes)} 个场景")

    for scene in scenes:
        texts = []
        for seg in segments:
            # 重叠检查
            if seg["end"] >= scene.start_sec and seg["start"] <= scene.end_sec:
                texts.append(seg["text"])
        scene.transcript = " ".join(texts).strip()

    covered = sum(1 for s in scenes if s.transcript)
    print(f"  {covered}/{len(scenes)} 个场景有文本覆盖")
    return scenes


# ─── 获取视频时长 ──────────────────────────────────────────────────────────────

def get_video_duration(video_path: Path) -> float:
    """使用 ffprobe 获取视频时长（秒）"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
        return 0.0


# ─── 输出 meeting_data.json ────────────────────────────────────────────────────

def save_meeting_data(
    scenes: list[Scene],
    video_path: Path,
    output_dir: Path,
    language: str,
    transcription_source: str,
    duration_sec: float,
    processing_time_sec: float,
) -> Path:
    """将处理结果保存为结构化的 meeting_data.json"""
    # 构建完整转录文本
    full_transcript_parts = []
    for scene in scenes:
        if scene.transcript:
            full_transcript_parts.append(
                f"[{scene.start_time} - {scene.end_time}] {scene.transcript}"
            )

    meeting_data = {
        "metadata": {
            "video_path": str(video_path),
            "duration_sec": round(duration_sec, 1),
            "total_scenes": len(scenes),
            "language": language,
            "transcription_source": transcription_source,
            "processing_time_sec": round(processing_time_sec, 1),
        },
        "scenes": [
            {
                "index": scene.index,
                "start_sec": round(scene.start_sec, 1),
                "end_sec": round(scene.end_sec, 1),
                "start_time": scene.start_time,
                "end_time": scene.end_time,
                "screenshot_path": str(scene.image_path) if scene.image_path else None,
                "transcript": scene.transcript,
            }
            for scene in scenes
        ],
        "full_transcript": "\n".join(full_transcript_parts),
    }

    output_path = output_dir / "meeting_data.json"
    output_path.write_text(
        json.dumps(meeting_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  结构化数据已保存 → {output_path}")
    return output_path


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="会议视频处理器 — 提取关键帧 + 转录/字幕解析 + 结构化输出"
    )
    parser.add_argument(
        "--video", required=True,
        help="视频文件路径",
    )
    parser.add_argument(
        "--subtitle",
        help="外部字幕文件路径 (.srt/.vtt/.json/.txt)",
    )
    parser.add_argument(
        "--output", default="./meeting_output",
        help="输出目录 (默认: ./meeting_output)",
    )
    parser.add_argument(
        "--whisper-model", default="base",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        help="Whisper 模型大小 (默认: base)",
    )
    parser.add_argument(
        "--language", default="zh",
        help="转录语言代码 (默认: zh)",
    )
    parser.add_argument(
        "--adaptive-threshold", type=float, default=3.5,
        help="场景检测灵敏度，越大越不灵敏 (默认: 3.5)",
    )
    parser.add_argument(
        "--min-scene-len", type=float, default=3.0,
        help="最短场景秒数 (默认: 3.0)",
    )
    parser.add_argument(
        "--downscale", type=int, default=2,
        help="视频降采样倍数 (默认: 2)",
    )
    parser.add_argument(
        "--skip-keyframes", action="store_true",
        help="跳过关键帧提取",
    )
    parser.add_argument(
        "--skip-transcription", action="store_true",
        help="跳过 Whisper 转录（需提供 --subtitle）",
    )
    args = parser.parse_args()

    start_time = time.time()

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"[错误] 视频文件不存在: {video_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    screenshots_dir = output_dir / "screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 判断需要哪些依赖
    need_scenedetect = not args.skip_keyframes
    need_whisper = not args.skip_transcription and not args.subtitle
    check_dependencies(need_scenedetect=need_scenedetect, need_whisper=need_whisper)

    print(f"\n{'='*50}")
    print(f"  会议视频处理器")
    print(f"{'='*50}")
    print(f"  视频: {video_path}")
    print(f"  输出: {output_dir}")
    if args.subtitle:
        print(f"  字幕: {args.subtitle}")
    print()

    # 获取视频时长
    duration_sec = get_video_duration(video_path)
    if duration_sec > 0:
        print(f"  视频时长: {_format_time(duration_sec)} ({duration_sec:.0f}s)")

    # Step 1: 关键帧提取
    scenes = []
    if not args.skip_keyframes:
        scenes = extract_keyframes(
            video_path=video_path,
            output_dir=screenshots_dir,
            adaptive_threshold=args.adaptive_threshold,
            min_scene_len_sec=args.min_scene_len,
            downscale=args.downscale,
        )
        if not scenes:
            print("[警告] 未提取到任何场景，将使用整个视频作为单一场景")
            scenes = [Scene(
                index=1,
                start_sec=0.0,
                end_sec=duration_sec if duration_sec > 0 else 9999.0,
            )]
    else:
        print("\n[1/3] 跳过关键帧提取")
        # 无截图时创建单一场景
        scenes = [Scene(
            index=1,
            start_sec=0.0,
            end_sec=duration_sec if duration_sec > 0 else 9999.0,
        )]

    # Step 2: 转录/字幕解析
    transcription_source = "none"
    segments = []

    if args.subtitle:
        subtitle_path = Path(args.subtitle)
        if not subtitle_path.exists():
            print(f"[错误] 字幕文件不存在: {subtitle_path}")
            sys.exit(1)
        print(f"\n[2/3] 正在加载外部字幕文件")
        segments = parse_subtitle(subtitle_path)
        transcription_source = subtitle_path.suffix.lstrip(".").lower()
        print(f"  已加载 {len(segments)} 个字幕片段")
    elif args.skip_transcription:
        print("\n[2/3] 跳过转录")
    else:
        segments = transcribe_audio(
            video_path=video_path,
            output_dir=output_dir,
            model_name=args.whisper_model,
            language=args.language,
        )
        transcription_source = "whisper"

    # Step 3: 对齐
    if segments:
        scenes = align_transcript_to_scenes(scenes, segments)
    else:
        print("\n[3/3] 无转录数据，跳过对齐")

    # 保存结构化输出
    processing_time = time.time() - start_time
    output_path = save_meeting_data(
        scenes=scenes,
        video_path=video_path,
        output_dir=output_dir,
        language=args.language,
        transcription_source=transcription_source,
        duration_sec=duration_sec,
        processing_time_sec=processing_time,
    )

    print(f"\n{'='*50}")
    print(f"  处理完成!")
    print(f"{'='*50}")
    print(f"  场景数量: {len(scenes)}")
    print(f"  有文本覆盖: {sum(1 for s in scenes if s.transcript)}")
    print(f"  有截图: {sum(1 for s in scenes if s.image_path)}")
    print(f"  处理耗时: {processing_time:.1f}s")
    print(f"  输出文件: {output_path}")


if __name__ == "__main__":
    main()
