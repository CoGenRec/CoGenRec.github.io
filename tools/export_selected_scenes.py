#!/usr/bin/env python3
"""Export selected calibrated scenes and the AOP-cropped balloon scene.

Uses existing CPU-readable videos/caches; does not run inference or recalibrate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rgb_alignment import rgb_reference

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "project_page"
METHOD = "000_VarLen_OursDecoder_iter_010000"
FIRE_RUN = REPO / "output/real_tmrec_varlen_oursdecoder_iter010000_fireworks_on_ground_01_gpu7"
BALLOON_RUN = REPO / "output/real_tmrec_varlen_oursdecoder_iter010000_water_balloon_ratio100_gpu5"
RAILWAY_RUN = REPO / "output/real_tmrec_varlen_stage1_iter030000_railway_gpu7_native"
ENCODED_FPS = 60


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def video_command(out, suffix=""):
    stem = "comparison" + (f"-{suffix}" if suffix else "")
    color = ["-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "1280x720",
        "-framerate", str(ENCODED_FPS), "-i", "pipe:0", "-an",
        "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "15",
        "-g", "15", "-bf", "0", *color, "-movflags", "+faststart", str(out / f"{stem}.mp4"),
        "-an", "-c:v", "libvpx-vp9", "-threads", "4", "-row-mt", "1",
        "-deadline", "good", "-cpu-used", "4", "-b:v", "0", "-crf", "22", "-g", "15",
        *color, str(out / f"{stem}.webm"),
    ]


def fireworks_frames():
    source = FIRE_RUN / "fireworks_on_ground_01_calibrated.mp4"
    capture = cv2.VideoCapture(str(source))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 76
    frame_index = 0
    previous_end = None
    try:
        for cop in range(455, 458):
            stem = f"csv000_row000000_cop{cop:06d}.npz"
            with np.load(FIRE_RUN / "_cache/reference" / stem, allow_pickle=False) as ref:
                assert int(ref["ratio"]) == 25
                assert np.array_equal(ref["select_aops"], np.arange(26))
                if previous_end is not None:
                    assert np.array_equal(previous_end, ref["rgb_start"])
                previous_end = ref["rgb_end"].copy()
                # The specified calibrated video retains the preceding interval's
                # endpoint, then omits the next interval's duplicated AOP 0.
                for aop in range(0 if cop == 455 else 1, 26):
                    ok, bgr = capture.read()
                    assert ok, (frame_index, cop, aop)
                    calibrated = cv2.cvtColor(bgr[362:682, :640], cv2.COLOR_BGR2RGB)
                    rgb_key = rgb_reference(aop, 0, 25)
                    yield {"cop": cop, "aop": aop, "calibrated_video_frame": frame_index,
                           "rgb_reference": rgb_key, "rgb_cop": cop+(rgb_key == 'rgb_end')}, (
                        ref[rgb_key], ref["td"][aop], ref["sd"][aop], calibrated)
                    frame_index += 1
        assert frame_index == 76
        assert not capture.read()[0]
    finally:
        capture.release()


def balloon_frames():
    stem = "csv000_row000000_cop000054.npz"
    with np.load(BALLOON_RUN / "_cache/reference" / stem, allow_pickle=False) as ref, np.load(
        BALLOON_RUN / "_cache/methods" / METHOD / stem, allow_pickle=False
    ) as pred:
        assert int(ref["ratio"]) == 100
        assert np.array_equal(ref["select_aops"], np.arange(101))
        for aop in (80, 100):
            exported = BALLOON_RUN / f"cop000054_frame_exports/reconstruction_all_101/frame_{aop:03d}_aop_{aop:03d}.png"
            assert np.array_equal(np.asarray(Image.open(exported).convert("RGB")), pred["frames"][aop])
        for aop in range(80, 101):
            rgb_key = rgb_reference(aop, 80, 100)
            yield {"cop": 54, "aop": aop, "rgb_reference": rgb_key,
                   "rgb_cop": 54+(rgb_key == 'rgb_end')}, (
                ref[rgb_key], ref["td"][aop], ref["sd"][aop], pred["frames"][aop])


def railway_frames():
    source = RAILWAY_RUN / "railway_calibrated.mp4"
    references = sorted((RAILWAY_RUN / "_cache/reference").glob("*.npz"))
    cops = [int(path.stem.rsplit("cop", 1)[1]) for path in references]
    assert cops == list(range(77, 88))
    capture = cv2.VideoCapture(str(source))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == len(cops) * 50 + 1
    # The supplied calibrated video keeps the preceding endpoint and omits
    # the following AOP 0, so COP 79 / AOP 10 is source frame 110.
    source_index = (79 - cops[0]) * 50 + 10
    assert capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
    previous_end = None
    try:
        for cop in range(79, 82):
            stem = f"csv000_row000000_cop{cop:06d}.npz"
            with np.load(RAILWAY_RUN / "_cache/reference" / stem, allow_pickle=False) as ref:
                assert int(ref["ratio"]) == 50
                assert np.array_equal(ref["select_aops"], np.arange(51))
                if previous_end is not None:
                    assert np.array_equal(previous_end, ref["rgb_start"])
                previous_end = ref["rgb_end"].copy()
                for aop in range(10 if cop == 79 else 1, 26 if cop == 81 else 51):
                    ok, bgr = capture.read()
                    assert ok, (source_index, cop, aop)
                    calibrated = cv2.cvtColor(bgr[362:682, :640], cv2.COLOR_BGR2RGB)
                    rgb_key = rgb_reference(aop, 0, 50)
                    yield {"cop": cop, "aop": aop, "calibrated_video_frame": source_index,
                           "rgb_reference": rgb_key, "rgb_cop": cop+(rgb_key == 'rgb_end')}, (
                        ref[rgb_key], ref["td"][aop], ref["sd"][aop], calibrated)
                    source_index += 1
        assert source_index == 226
    finally:
        capture.release()


def export_scene(slug, title, fps, count, generator, preview_factors, poster_frame, top_crop, metadata):
    out = PAGE / "assets" / slug
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    canvas = Image.new("RGB", (1280, 720), "#142333")
    draw = ImageDraw.Draw(canvas)
    locations = [(0, 0), (640, 0), (0, 360), (640, 360)]
    for label, (x, y) in zip(("RGB", "TD", "SD", "CoGenRec"), locations):
        draw.text((x + 16, y + 8), label, font=font,
                  fill="#b7ccff" if label == "CoGenRec" else "#e7edf5")
        draw.text((x + 624, y + 11), "~30 FPS" if label == "RGB" else f"{fps} FPS",
                  font=small, fill="#a5b4c5", anchor="ra")
    previews = {}
    for factor in preview_factors:
        n = int(np.ceil(count * ENCODED_FPS * factor / fps))
        indices = [count // 2] if n == 1 else [min(count - 1, int(np.floor(i * fps / (ENCODED_FPS * factor) + .5))) for i in range(n)]
        previews[factor] = {"source_frames": indices, "data": []}
    encoder = subprocess.Popen(video_command(out), stdin=subprocess.PIPE)
    frame_map = []
    try:
        for index, (info, arrays) in enumerate(generator()):
            for array, (x, y) in zip(arrays, locations):
                assert array.shape == (320, 640, 3) and array.dtype == np.uint8
                # The calibrated MP4 has a 36-pixel burned-in label over the
                # prediction. Crop the same rows in every view and letterbox,
                # preserving aspect ratio and spatial alignment of all panels.
                image = Image.fromarray(array[top_crop:])
                canvas.paste(image, (x, y + 40 + top_crop // 2))
            payload = canvas.tobytes()
            encoder.stdin.write(payload)
            for preview in previews.values():
                if index in preview["source_frames"]:
                    preview["data"].append(payload)
            if index == poster_frame:
                canvas.save(out / "poster.jpg", quality=95, subsampling=0)
            frame_map.append({"frame": index, **info,
                              "capture_time_seconds": index / fps,
                              "video_time_seconds": index / ENCODED_FPS})
    finally:
        encoder.stdin.close()
        code = encoder.wait()
    assert code == 0 and len(frame_map) == count
    for factor, preview in previews.items():
        suffix = "original" if factor == 1 else f"slow{factor}"
        process = subprocess.Popen(video_command(out, suffix), stdin=subprocess.PIPE)
        try:
            for payload in preview["data"]:
                process.stdin.write(payload)
        finally:
            process.stdin.close()
            code = process.wait()
        assert code == 0
    manifest = {
        "title": title, "frame_count": count, "nominal_source_fps": fps,
        "encoded_fps": ENCODED_FPS, "capture_duration_seconds": count / fps,
        "capture_timestamp_span_seconds": (count - 1) / fps,
        "common_top_crop_px": top_crop,
        "crop_policy": "Same top crop in all four views; centered with black padding, no stretch",
        "synchronization": "All four views baked into one video frame",
        "rgb_policy": "First half of each COP interval uses rgb_start; second half uses rgb_end; exact midpoint uses rgb_start",
        "fast_preview_factors": preview_factors,
        "fast_previews": {str(f): {"source_frames": p["source_frames"], "duration_seconds": len(p["source_frames"]) / ENCODED_FPS} for f, p in previews.items()},
        "fast_preview_policy": "Display-rate sampling; sub-refresh clips use one representative middle sample; frame stepping always uses the complete master",
        "frames": frame_map, **metadata,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"scene": slug, "frames": count, "capture_seconds": count / fps, "preview_factors": preview_factors}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", choices=("fireworks", "balloon", "railway", "all"), default="all", nargs="?")
    args = parser.parse_args()
    if args.scene in ("fireworks", "all"):
        source = FIRE_RUN / "fireworks_on_ground_01_calibrated.mp4"
        refs = [FIRE_RUN / f"_cache/reference/csv000_row000000_cop{cop:06d}.npz" for cop in range(455, 458)]
        export_scene("fireworks-cop455-457", "Ground fireworks", 757, 76, fireworks_frames,
                     [1, 2], 38, 36, {
                         "cop_range_inclusive": [455, 457], "ratio": 25,
                         "rgb_switch_aop": 13,
                         "source_run": str(FIRE_RUN), "calibrated_source": str(source),
                         "calibrated_source_sha256": sha256(source),
                         "calibration_policy": "Use the supplied calibrated MP4 prediction tile directly; no recalibration",
                         "calibrated_prediction_crop_xywh": [0, 362, 640, 320],
                         "endpoint_policy": "Retain previous interval endpoint, omit next interval AOP 0, matching calibrated video",
                         "references": [{"path": str(p), "sha256": sha256(p)} for p in refs],
                     })
    if args.scene in ("balloon", "all"):
        stem = "csv000_row000000_cop000054.npz"
        sources = [BALLOON_RUN / "_cache/reference" / stem, BALLOON_RUN / "_cache/methods" / METHOD / stem]
        export_scene("balloon-cop54-aop80-100", "Balloon burst", 3000, 21, balloon_frames,
                     [1, 2, 4, 8, 16], 13, 0, {
                         "cop": 54, "aop_range_inclusive": [80, 100], "ratio": 100,
                         "rgb_policy": "Split the selected AOP 80..100 window: 80..90 use rgb_start; 91..100 use rgb_end (intentional display mapping)",
                         "rgb_split_window_inclusive": [80, 100], "rgb_switch_aop": 91,
                         "source_run": str(BALLOON_RUN), "source_scene": "water_balloon_small_3030_06",
                         "rate_basis": "3000 FPS presentation as requested; source directory names the nominal 3030 mode",
                         "endpoint_policy": "AOP 80 through 100 inclusive, including both requested PNG positions",
                         "sources": [{"path": str(p), "sha256": sha256(p)} for p in sources],
                     })
    if args.scene in ("railway", "all"):
        source = RAILWAY_RUN / "railway_calibrated.mp4"
        refs = [RAILWAY_RUN / f"_cache/reference/csv000_row000000_cop{cop:06d}.npz" for cop in range(79, 82)]
        export_scene("railway-cop79-aop10-cop81-aop25", "Train encounter", 1515, 116, railway_frames,
                     [1, 2, 4], 10, 36, {
                         "cop_range_inclusive": [79, 81], "ratio": 50,
                         "rgb_switch_aop": 26,
                         "relative_speed_kmh": 600,
                         "first_sample": {"cop": 79, "aop": 10},
                         "last_sample": {"cop": 81, "aop": 25},
                         "source_run": str(RAILWAY_RUN), "calibrated_source": str(source),
                         "calibrated_source_sha256": sha256(source),
                         "calibration_policy": "Use the supplied calibrated MP4 prediction tile directly; no recalibration",
                         "calibrated_prediction_crop_xywh": [0, 362, 640, 320],
                         "calibrated_video_frame_range_inclusive": [110, 225],
                         "endpoint_policy": "Retain previous interval endpoint, omit next interval AOP 0, matching calibrated video",
                         "references": [{"path": str(p), "sha256": sha256(p)} for p in refs],
                     })


if __name__ == "__main__":
    main()
