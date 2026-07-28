"""ffmpeg mux / transcode / audio extract, with GPU hardware acceleration probe.

- merge_av: copy-mux DASH video(m4s)+audio(m4s) into .mp4/.mkv (无损, 秒级)
- transcode: re-encode H.264/H.265, auto GPU (NVENC > QSV > AMF > VideoToolbox > CPU)
- extract_audio: mp3 / m4a(copy) / webm(opus) / flac(copy Hi-Res)
- flv_to_mp4: remux ancient FLV downloads
"""
import os
import sys
import shutil
import subprocess


def _ffmpeg_candidates():
    cands = []
    env = os.environ.get("BILI_FFMPEG")
    if env:
        cands.append(env)
    # PyInstaller one-file extraction dir, or this script's directory
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"))
    cands.append(os.path.join(base, "ffmpeg.exe"))
    cands.append(os.path.join(base, "ffmpeg", "ffmpeg.exe"))
    # imageio-ffmpeg ships a static ffmpeg binary (used for the standalone build)
    try:
        import imageio_ffmpeg
        cands.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    cands.append("ffmpeg")
    return cands


def get_ffmpeg():
    """Resolve a usable ffmpeg binary (bundled > imageio > PATH)."""
    for c in _ffmpeg_candidates():
        try:
            p = subprocess.run([c, "-version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10)
            if p.returncode == 0:
                return c
        except Exception:
            continue
    return "ffmpeg"


FFMPEG = get_ffmpeg()

_gpu_cache = None


def has_ffmpeg():
    return FFMPEG != "ffmpeg"


def _run(args, desc="", cwd=None):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=cwd)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "ignore")[-800:]
        raise RuntimeError(f"ffmpeg 失败 ({desc}):\n{tail}")


def detect_gpu_encoders():
    """Return dict {'h264': encoder, 'hevc': encoder} using best available HW."""
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache
    result = {"h264": "libx264", "hevc": "libx265"}
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=15).stdout.decode("utf-8", "ignore")
    except Exception:
        _gpu_cache = result
        return result
    for prefix in ("nvenc", "qsv", "amf", "videotoolbox"):
        h264 = f"h264_{prefix}"
        hevc = f"hevc_{prefix}"
        if h264 in out or hevc in out:
            # verify encoder actually initializes (driver present)
            if h264 in out and _probe_encoder(h264):
                result["h264"] = h264
                if hevc in out and _probe_encoder(hevc):
                    result["hevc"] = hevc
                break
    _gpu_cache = result
    return result


def _probe_encoder(enc):
    try:
        p = subprocess.run(
            [FFMPEG, "-hide_banner", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
             "-c:v", enc, "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return p.returncode == 0
    except Exception:
        return False


def merge_av(video_path, audio_path, out_path):
    """Lossless mux DASH streams into MP4 (or MKV if extension says so)."""
    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    args += ["-i", video_path]
    if audio_path:
        args += ["-i", audio_path]
    args += ["-c", "copy"]
    if out_path.lower().endswith(".mp4"):
        args += ["-movflags", "+faststart"]
    args += [out_path]
    _run(args, "混流")
    return out_path


def transcode(in_path, out_path, codec="h264", gpu=False, crf=23, preset="medium"):
    """Re-encode video stream; audio copied."""
    enc_map = detect_gpu_encoders() if gpu else {"h264": "libx264", "hevc": "libx265"}
    enc = enc_map["hevc" if codec in ("hevc", "h265") else "h264"]
    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", in_path,
            "-c:v", enc]
    if enc.startswith("lib"):
        args += ["-crf", str(crf), "-preset", preset]
    elif "nvenc" in enc:
        args += ["-rc", "vbr", "-cq", str(crf), "-preset", "p5"]
    elif "qsv" in enc:
        args += ["-global_quality", str(crf)]
    args += ["-c:a", "copy", "-movflags", "+faststart", out_path]
    print(f"  转码中: {os.path.basename(in_path)} -> {enc} ...")
    _run(args, f"转码 {enc}")
    return out_path


def extract_audio(in_path, out_path, fmt="m4a"):
    """Extract/convert audio only. fmt: mp3 / m4a / webm / flac."""
    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", in_path, "-vn"]
    fmt = fmt.lower()
    if fmt == "mp3":
        args += ["-c:a", "libmp3lame", "-q:a", "0"]
    elif fmt == "m4a":
        args += ["-c:a", "copy"]
    elif fmt == "webm":
        args += ["-c:a", "libopus", "-b:a", "192k"]
    elif fmt == "flac":
        args += ["-c:a", "flac"]
    else:
        args += ["-c:a", "copy"]
    root = os.path.splitext(out_path)[0]
    out_path = f"{root}.{fmt}"
    try:
        _run(args + [out_path], f"提取音频 {fmt}")
    except RuntimeError:
        if fmt == "m4a":  # source may be flac/eac3 that mp4 can't hold via copy
            _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", in_path,
                  "-vn", "-c:a", "aac", "-b:a", "256k", out_path], "提取音频 aac")
        else:
            raise
    return out_path


def flv_to_mp4(in_path, out_path):
    _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
          "-i", in_path, "-c", "copy", "-movflags", "+faststart", out_path],
         "FLV 转 MP4")
    return out_path


def burn_subtitle(video_path, sub_path, out_path, sub_type="ass", font_size=24):
    """把字幕硬烧进画面（⑧）。sub_type: 'ass' | 'srt'。

    Windows 下 ffmpeg 的 subtitles 滤镜会把盘符 "C:" 的冒号解析为
    选项分隔符导致失败，因此切到字幕所在目录用相对文件名。
    """
    if not has_ffmpeg():
        raise RuntimeError("未检测到 ffmpeg，无法烧录字幕")
    video_path = os.path.abspath(video_path)
    out_path = os.path.abspath(out_path)
    sub_dir = os.path.dirname(os.path.abspath(sub_path)) or "."
    sub_name = os.path.basename(sub_path)
    # 滤镜内需转义单引号；相对文件名规避盘符冒号问题
    esc = sub_name.replace("'", r"\'")
    force = f"force_style='FontSize={font_size},Alignment=2'"
    vf = f"subtitles='{esc}':{force}"
    _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-i", video_path, "-vf", vf, "-c:a", "copy", out_path],
         "字幕硬烧", cwd=sub_dir)
    return out_path


def cut(video_path, out_path, start, end=None):
    """片段截取（⑧）：start/end 形如 '00:01:30' 或秒数。"""
    if not has_ffmpeg():
        raise RuntimeError("未检测到 ffmpeg，无法裁剪")
    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start)]
    if end:
        args += ["-to", str(end)]
    args += ["-i", video_path, "-c", "copy", out_path]
    try:
        _run(args, "片段截取")
    except RuntimeError:
        # 关键帧不整除时 -c copy 可能失败，回退重新编码
        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(start)]
        if end:
            args += ["-to", str(end)]
        args += ["-i", video_path, "-c:v", "libx264", "-c:a", "aac", out_path]
        _run(args, "片段截取(重编码)")
    return out_path


def merge_playlist(files, out_path, titles=None):
    """多 P 合并为单文件（⑧），可选章节标题。"""
    if not has_ffmpeg():
        raise RuntimeError("未检测到 ffmpeg，无法合并")
    if len(files) == 1:
        import shutil
        shutil.copy(files[0], out_path)
        return out_path
    import tempfile
    base = os.path.splitext(out_path)[0]
    lst = base + ".concat.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p in files:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")
    try:
        _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", lst,
               "-c", "copy", out_path], "多P合并")
    finally:
        try:
            os.remove(lst)
        except OSError:
            pass
    # 注入章节（如提供了标题）
    if titles and len(titles) == len(files):
        _inject_chapters(out_path, titles)
    return out_path


def _inject_chapters(mp4_path, titles):
    """用 metadata 注入简单章节标记。"""
    import tempfile
    meta = os.path.splitext(mp4_path)[0] + ".chapters.txt"
    dur = _probe_duration(mp4_path)
    if dur <= 0:
        return
    seg = dur / len(titles)
    with open(meta, "w", encoding="utf-8") as f:
        for i, t in enumerate(titles):
            f.write(f"[CHAPTER]\nTIMEBASE=1\nSTART={int(i*seg)}\n"
                    f"END={int((i+1)*seg)}\ntitle={t}\n\n")
    tmp = mp4_path + ".chaptmp.mp4"
    try:
        _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-i", mp4_path, "-i", meta, "-map_chapters", "1",
               "-c", "copy", tmp], "注入章节")
        os.replace(tmp, mp4_path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
    finally:
        try:
            os.remove(meta)
        except OSError:
            pass


def _probe_duration(path):
    try:
        out = subprocess.run(
            [FFMPEG, "-hide_banner", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", "-i", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15
        ).stdout.decode("utf-8", "ignore").strip()
        return float(out) if out else 0
    except Exception:
        return 0


def ai_subtitle(in_path, out_dir, lang="zh", model="base"):
    """AI 字幕生成（⑨，可选功能，需本地 faster-whisper）。

    自动识别语音并生成 out_dir/<name>.srt。未安装依赖时给出明确提示。
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "AI 字幕需要 faster-whisper：pip install faster-whisper "
            "（首次使用会自动下载模型，约 140MB）")
    if not os.path.isfile(in_path):
        raise RuntimeError(f"音视频文件不存在: {in_path}")
    base = os.path.splitext(os.path.basename(in_path))[0]
    out_srt = os.path.join(out_dir, f"{base}.srt")
    md = WhisperModel(model, device="auto", compute_type="int8")
    segs = list(md.transcribe(in_path, language=lang, beam_size=5)[0])
    _write_srt(segs, out_srt)
    return out_srt


def _write_srt(segments, path):
    def _t(s):
        h, r = divmod(int(s), 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{int((s % 1) * 1000):03d}"
    with open(path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segs, 1):
            f.write(f"{i}\n{_t(seg.start)} --> {_t(seg.end)}\n"
                    f"{seg.text.strip()}\n\n")
