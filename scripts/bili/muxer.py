"""ffmpeg mux / transcode / audio extract, with GPU hardware acceleration probe.

- merge_av: copy-mux DASH video(m4s)+audio(m4s) into .mp4/.mkv (无损, 秒级)
- transcode: re-encode H.264/H.265, auto GPU (NVENC > QSV > AMF > VideoToolbox > CPU)
- extract_audio: mp3 / m4a(copy) / webm(opus) / flac(copy Hi-Res)
- flv_to_mp4: remux ancient FLV downloads
"""
import os
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

_gpu_cache = None


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def _run(args, desc=""):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
