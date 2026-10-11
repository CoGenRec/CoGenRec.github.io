#!/usr/bin/env python3
"""Export the selected cup scene from existing visualization caches.

Run with a Python environment containing numpy and Pillow, for example:
  /home/yapeng/anaconda3/envs/pro6000/bin/python project_page/tools/export_cup_scene.py

No inference or raw-data processing is performed. The four panels are stored in
one video frame so that seeking, playback, and slow motion cannot desynchronize
them. COP 66..70 are five cached intervals, each with AOP 0..25 inclusive. Keep
0..24 from every interval to avoid repeating shared endpoints at the joins.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rgb_alignment import rgb_reference


REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUN = REPO / "output/real_tmrec_260921_4duse_varlen_oursdecoder_iter010000_ratio25_gpu6"
DEFAULT_OUT = REPO / "project_page/assets/cup-shattering-cop66-70"
METHOD = "000_VarLen_OursDecoder_iter_010000"
ENCODED_FPS = 60
SOURCE_FPS = 757  # Nominal acquisition mode, not resolved_run.json's export FPS.
RATIO = 25
FIRST_COP, LAST_COP = 66, 70
WIDTH, HEIGHT, HEADER = 640, 320, 40


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 19)
    small = ImageFont.truetype(font_path, 15)
    canvas = Image.new("RGB", (WIDTH * 2, (HEIGHT + HEADER) * 2), "#142333")
    draw = ImageDraw.Draw(canvas)
    panels = [
        ("RGB", "30 FPS", (0, 0)),
        ("TD", "757 FPS", (WIDTH, 0)),
        ("SD", "757 FPS", (0, HEIGHT + HEADER)),
        ("CoGenRec", "757 FPS", (WIDTH, HEIGHT + HEADER)),
    ]
    for label, fps, (x, y) in panels:
        draw.text((x + 16, y + 8), label, font=font,
                  fill="#b7ccff" if label == "CoGenRec" else "#e7edf5")
        draw.text((x + WIDTH - 16, y + 11), fps, font=small,
                  fill="#a5b4c5", anchor="ra")

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", "1280x720", "-framerate", str(ENCODED_FPS),
        "-i", "pipe:0", "-an", "-c:v", "libx264", "-threads", "4",
        "-preset", "medium", "-crf", "15", "-g", "15", "-bf", "0",
        "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-movflags", "+faststart", str(args.out / "comparison.mp4"),
        "-an", "-c:v", "libvpx-vp9", "-threads", "4", "-row-mt", "1",
        "-deadline", "good", "-cpu-used", "4", "-b:v", "0", "-crf", "22", "-g", "15",
        "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        str(args.out / "comparison.webm"),
    ]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = []
    sources = []
    previews = {}
    for factor in (1, 2):
        count = int(np.ceil((LAST_COP - FIRST_COP + 1) * RATIO * ENCODED_FPS * factor / SOURCE_FPS))
        indices = [min(124, int(np.floor(i * SOURCE_FPS / (ENCODED_FPS * factor) + 0.5))) for i in range(count)]
        previews[factor] = {"source_frames": indices, "data": []}
    previous_rgb_end = None
    try:
        for cop in range(FIRST_COP, LAST_COP + 1):
            stem = f"csv000_row000001_cop{cop:06d}.npz"
            reference_path = args.run / "_cache/reference" / stem
            method_path = args.run / "_cache/methods" / METHOD / stem
            with np.load(reference_path, allow_pickle=False) as ref, np.load(method_path, allow_pickle=False) as result:
                assert int(ref["ratio"]) == RATIO
                assert np.array_equal(ref["select_aops"], np.arange(RATIO + 1))
                for arr in (ref["td"], ref["sd"], result["frames"]):
                    assert arr.shape == (RATIO + 1, HEIGHT, WIDTH, 3)
                    assert arr.dtype == np.uint8
                if previous_rgb_end is not None:
                    assert np.array_equal(previous_rgb_end, ref["rgb_start"]), f"RGB discontinuity at COP {cop}"
                previous_rgb_end = ref["rgb_end"].copy()
                for aop in range(RATIO):
                    rgb_key = rgb_reference(aop, 0, RATIO)
                    arrays = (ref[rgb_key], ref["td"][aop], ref["sd"][aop], result["frames"][aop])
                    for arr, (_, _, (x, y)) in zip(arrays, panels):
                        canvas.paste(Image.fromarray(arr), (x, y + HEADER))
                    frame_index = len(frames)
                    frame_bytes = canvas.tobytes()
                    encoder.stdin.write(frame_bytes)
                    for preview in previews.values():
                        if frame_index in preview["source_frames"]:
                            preview["data"].append(frame_bytes)
                    if cop == 67 and aop == 13:
                        canvas.save(args.out / "poster.jpg", quality=95, subsampling=0)
                    frames.append({
                        "frame": frame_index, "cop": cop, "aop": aop,
                        "rgb_reference": rgb_key, "rgb_cop": cop+(rgb_key == 'rgb_end'),
                        "video_time_seconds": frame_index / ENCODED_FPS,
                        "capture_time_seconds": frame_index / SOURCE_FPS,
                    })
            sources.append({
                "cop": cop,
                "reference": str(reference_path.relative_to(args.run)),
                "reference_sha256": sha256(reference_path),
                "reconstruction": str(method_path.relative_to(args.run)),
                "reconstruction_sha256": sha256(method_path),
            })
    finally:
        encoder.stdin.close()
        returncode = encoder.wait()
    if returncode:
        raise RuntimeError(f"ffmpeg failed: {returncode}")
    # At original acquisition speed a 757 FPS file can exceed a browser's
    # decoder throughput, even though the display presents only ~60 FPS. Make
    # deterministic 60 FPS previews for the two fastest settings; slower speeds
    # and frame stepping retain all 125 samples in the master video.
    for factor, preview in previews.items():
        suffix = "original" if factor == 1 else "slow2"
        preview_command = [
            item.replace("comparison.mp4", f"comparison-{suffix}.mp4")
                .replace("comparison.webm", f"comparison-{suffix}.webm")
            for item in command
        ]
        process = subprocess.Popen(preview_command, stdin=subprocess.PIPE)
        try:
            for frame_bytes in preview["data"]:
                process.stdin.write(frame_bytes)
        finally:
            process.stdin.close()
            code = process.wait()
        if code:
            raise RuntimeError(f"Preview ffmpeg failed: {code}")
    manifest = {
        "scene": "杯子摔碎", "title": "Shattering glass",
        "cop_range_inclusive": [FIRST_COP, LAST_COP],
        "csv_row_index": 1, "ratio": RATIO,
        "source_run": str(args.run.resolve()), "method": METHOD,
        "frame_count": len(frames), "encoded_fps": ENCODED_FPS,
        "nominal_source_fps": SOURCE_FPS,
        "nominal_rgb_fps": SOURCE_FPS / RATIO,
        "rate_basis": "757 FPS nominal acquisition mode; RGB approximately 30 FPS; cache ratio 25",
        "capture_duration_seconds": len(frames) / SOURCE_FPS,
        "encoded_duration_seconds": len(frames) / ENCODED_FPS,
        "playback_rate_formula": "nominal_source_fps / encoded_fps / slowdown",
        "fast_preview_policy": "Original and 2x slower use deterministic 60 FPS presentation samples at playbackRate 1; frame stepping always uses the complete master",
        "fast_previews": {
            str(factor): {"source_frames": preview["source_frames"], "encoded_fps": ENCODED_FPS,
                          "duration_seconds": len(preview["source_frames"]) / ENCODED_FPS}
            for factor, preview in previews.items()
        },
        "slowdown_factors": [1, 2, 4, 8, 16],
        "rgb_policy": "First half of each COP interval uses rgb_start; second half uses rgb_end; exact midpoint uses rgb_start",
        "rgb_switch_aop": RATIO//2+1,
        "endpoint_policy": "Keep AOP 0..24 per interval; omit shared right endpoint 25",
        "signal_policy": "Use cached TD and SD visualizations as supplied, including their zero first TD sample",
        "synchronization": "RGB, TD, SD, reconstruction baked into one video frame",
        "video_formats": ["H.264 MP4 (primary)", "VP9 WebM (fallback)"],
        "panel_order": ["RGB (top left)", "TD (top right)", "SD (bottom left)", "CoGenRec (bottom right)"],
        "sources": sources, "frames": frames,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("frame_count", "nominal_source_fps", "capture_duration_seconds")}, indent=2))
    print(f"Exported {args.out / 'comparison.mp4'}")


if __name__ == "__main__":
    main()
