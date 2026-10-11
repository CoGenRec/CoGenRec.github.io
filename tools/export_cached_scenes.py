#!/usr/bin/env python3
"""Export additional gallery scenes with raw TD and cached RGB/SD/CoGenRec.

The RGB, TD, SD and CoGenRec panels share one encoded frame. Retained AOPs
are held until the next actual sample, preserving capture timing and the
requested RGB midpoint switch. TD comes from the original sensor recording,
without the model input's segment integration or first-item reset. No inference
or calibration is performed.
"""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import numpy as np

from export_selected_scenes import PAGE, REPO, export_scene, sha256
from cache_sources import RUN, METHOD, AOPS, RATIO, SOURCE_FPS
from rgb_alignment import rgb_reference


SCENES = {
    'peach': {
        'source_scene': '桃花', 'title': 'Peach blossoms',
        'worker': 3, 'row': 55, 'first_cop': 26, 'last_cop': 28,
        'slug': 'peach-blossoms-cop26-28',
    },
    'bicycles': {
        'source_scene': '蓝绿单车', 'title': 'Street bicycles',
        'worker': 0, 'row': 66, 'first_cop': 98, 'last_cop': 100,
        'slug': 'street-bicycles-cop98-100',
    },
}
RAW_CSV = REPO / 'src/dataset/100demo_info.csv'


def stream_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def visualize_diff(diff):
    """Match test_TMRec_real._viz_diff_rgb without importing inference code."""
    value = np.clip(np.asarray(diff, dtype=np.float32), -1.0, 1.0).copy()
    value[np.abs(value) < 0.01] = 0.0
    value = np.clip(value * 16.0, -1.0, 1.0)
    rgb = np.zeros((*value.shape, 3), dtype=np.float32)
    rgb[..., 0] = np.maximum(-value, 0.0)
    rgb[..., 2] = np.maximum(value, 0.0)
    return (rgb * 255.0).round().astype(np.uint8)


def load_raw_measurements(spec):
    # Keep sensor decoding independent of dataset/model package initialization.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import torch
    from CBRDM.models_util import UpsampleTSDConv
    from tianmoucv.data import TianmoucDataReader

    with RAW_CSV.open(newline='', encoding='utf-8-sig') as source:
        matches = [row for row in csv.DictReader(source) if row['scene'] == spec['source_scene']]
    assert len(matches) == 1, (spec['source_scene'], matches)
    raw_path = Path(matches[0]['path'])
    exposure_path = sorted((raw_path / 'cone').glob('*.txt'))[0]
    exposure_us = int(re.search(r'Exp Time:(\d+)\s', exposure_path.read_text()).group(1))
    period = max(1, exposure_us // 1320)
    reader = TianmoucDataReader(str(raw_path), N=1, camera_idx=0,
                               showList=False, print_info=False)
    packs = {}
    for cop in range(spec['first_cop'], spec['last_cop'] + 2):
        key, relative_index = reader.locateSample(cop)
        packs[cop] = reader.packRead(relative_index, key, needPreProcess=False)
        assert packs[cop]['rawDiff'].shape == (3, RATIO + 1, 160, 160)

    measurements = {}
    upsample = UpsampleTSDConv()
    for cop in range(spec['first_cop'], spec['last_cop'] + 1):
        start, end = packs[cop], packs[cop + 1]
        # Match the existing dataset's REALDATA_OFFSET=1 and exposure center.
        # Preserve the measured TD at every position, including AOP 0.
        raw = torch.cat((start['rawDiff'][:, 1:-1],
                         end['rawDiff'][:, :period + 1]), dim=1) / 128.0
        offset = period // 2
        between = raw[:, offset:offset + RATIO + 1]
        assert between.shape == (3, RATIO + 1, 160, 160)
        selected = upsample(between[:, AOPS]).numpy()
        raw_indices = list(start['meta']['R_idx'][1:-1]) + list(end['meta']['R_idx'][:period + 1])
        raw_timestamps = list(start['meta']['R_timestamp'][1:-1]) + list(end['meta']['R_timestamp'][:period + 1])
        td = np.stack([visualize_diff(frame) for frame in selected[0]])
        sd = np.stack([visualize_diff(frame) for frame in selected[2]])
        measurements[cop] = {
            'td': td, 'sd': sd,
            'samples': [{'td_raw_rod_index': int(raw_indices[offset + aop]),
                         'td_raw_timestamp_us': int(raw_timestamps[offset + aop])}
                        for aop in AOPS],
        }
    rod_path = Path(packs[spec['first_cop']]['meta']['R_name'])
    metadata = {
        'csv': str(RAW_CSV), 'csv_sha256': sha256(RAW_CSV),
        'recording': str(raw_path),
        'rod_path': str(rod_path), 'rod_sha256': stream_sha256(rod_path),
        'exposure_info': str(exposure_path), 'exposure_info_sha256': sha256(exposure_path),
        'cone_exposure_us': exposure_us, 'cone_exposure_period': period,
        'realdata_offset': 1, 'exposure_center_offset': period // 2,
        'normalization': 'rawDiff / 128',
        'upsampling': 'UpsampleTSDConv, bilinear 320x640, horizontal flip',
        'visualization': {'threshold_before_gain': 0.01, 'gain': 16,
                          'negative': 'red', 'positive': 'blue'},
        'alignment_validation': 'Every selected raw SD image exactly equals the existing cached SD image',
    }
    return measurements, metadata


def load_scene(scene):
    spec = SCENES[scene]
    raw_measurements, raw_metadata = load_raw_measurements(spec)
    cache = RUN / f"_cache/worker_{spec['worker']:03d}"
    worker_path = RUN / f"_workers/worker_{spec['worker']:03d}/resolved_run.json"
    worker = json.loads(worker_path.read_text())
    assert worker['ratio'] == RATIO and worker['select_aops'] == AOPS
    assert worker['methods'][1]['label'] == 'Ours (with exposure augmentation)'
    segment_cops = sorted(
        int(Path(path).stem.rsplit('cop', 1)[1])
        for path in worker['segment_videos']
        if Path(path).parent.name == spec['source_scene']
    )
    assert all(cop in segment_cops for cop in range(spec['first_cop'], spec['last_cop'] + 1))
    sources, samples = [], []
    previous_end = None
    for interval, cop in enumerate(range(spec['first_cop'], spec['last_cop'] + 1)):
        stem = f"csv000_row{spec['row']:06d}_cop{cop:06d}.npz"
        reference_path = cache / 'reference' / stem
        prediction_path = cache / 'methods' / METHOD / stem
        sources.extend((reference_path, prediction_path))
        with np.load(reference_path, allow_pickle=False) as ref, np.load(
            prediction_path, allow_pickle=False
        ) as prediction:
            for array in (ref['td'], ref['sd'], prediction['frames']):
                assert array.shape == (len(AOPS), 320, 640, 3) and array.dtype == np.uint8
            for key in ('rgb_start', 'rgb_end'):
                assert ref[key].shape == (320, 640, 3) and ref[key].dtype == np.uint8
            if previous_end is not None:
                assert np.array_equal(previous_end, ref['rgb_start'])
            previous_end = ref['rgb_end'].copy()
            # Independently verify the raw TD's time/space mapping using SD,
            # whose selected samples were not altered by segment integration.
            assert np.array_equal(raw_measurements[cop]['sd'], ref['sd']), (scene, cop)
            for index, aop in enumerate(AOPS):
                tick = interval * RATIO + aop
                rgb_key = rgb_reference(aop, 0, RATIO)
                info = {
                    'sample': len(samples), 'cop': cop, 'aop': aop,
                    'rgb_reference': rgb_key, 'rgb_cop': cop + (rgb_key == 'rgb_end'),
                    'source_sample_tick': tick,
                    'source_sample_time_seconds': tick / SOURCE_FPS,
                    'source_scene_video_frame': (cop - segment_cops[0]) * len(AOPS) + index,
                    **raw_measurements[cop]['samples'][index],
                }
                arrays = tuple(array.copy() for array in (
                    ref[rgb_key], raw_measurements[cop]['td'][index], ref['sd'][index], prediction['frames'][index]
                ))
                samples.append((info, arrays))
    return samples, sources, worker_path, worker, raw_metadata


def held_frames(samples, duration_ticks):
    for index, (info, arrays) in enumerate(samples):
        next_tick = samples[index + 1][0]['source_sample_tick'] if index + 1 < len(samples) else duration_ticks
        for tick in range(info['source_sample_tick'], next_tick):
            yield {**info, 'held_display_tick': tick}, arrays


def export(scene):
    spec = SCENES[scene]
    samples, sources, worker_path, worker, raw_metadata = load_scene(scene)
    duration_ticks = (spec['last_cop'] - spec['first_cop'] + 1) * RATIO
    source_video = RUN / 'scenes' / f"{spec['source_scene']}.mp4"
    # Publish complete encoded files only after all formats/previews succeed.
    with tempfile.TemporaryDirectory(prefix='.raw-td-', dir=PAGE / 'assets') as staging:
        staging_path = Path(staging)
        export_scene(
            staging_path.name, spec['title'], SOURCE_FPS, duration_ticks,
            lambda: held_frames(samples, duration_ticks), [1, 2], duration_ticks // 2, 0,
            {
                'source_run': str(RUN), 'source_scene': spec['source_scene'],
                'source_video': str(source_video), 'source_video_sha256': sha256(source_video),
                'worker_manifest': str(worker_path), 'worker_manifest_sha256': sha256(worker_path),
                'method': METHOD, 'checkpoint_provenance': worker['methods'][1],
                'ratio': RATIO, 'cop_range_inclusive': [spec['first_cop'], spec['last_cop']],
                'select_aops': AOPS, 'rgb_switch_aop': RATIO // 2 + 1,
                'source_sample_count': len(samples),
                'source_samples': [info for info, _ in samples],
                'sample_ticks': [info['source_sample_tick'] for info, _ in samples],
                'duration_ticks': duration_ticks, 'encoded_frame_count': duration_ticks,
                'rate_basis': '757 FPS capture mode; source cache retains seven selected AOPs per COP',
                'td_policy': 'Original single-AOP sensor TD at each selected timestamp; no model-input integration or segment-start reset',
                'raw_td_source': raw_metadata,
                'timeline_policy': 'Hold each retained sample until the next real AOP at its original capture tick',
                'capture_time_semantics': 'frames.capture_time_seconds is the held display tick; source_sample_time_seconds is the retained sample timestamp',
                'endpoint_policy': 'Retain every cached AOP 0,4,8,12,16,20,24 in the requested COP intervals',
                'sources': [{'path': str(path), 'sha256': sha256(path)} for path in sources],
            },
        )
        destination = PAGE / 'assets' / spec['slug']
        destination.mkdir(parents=True, exist_ok=True)
        for path in staging_path.iterdir():
            os.replace(path, destination / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenes', choices=(*SCENES, 'all'), nargs='+')
    args = parser.parse_args()
    for scene in SCENES:
        if scene in args.scenes or 'all' in args.scenes:
            export(scene)


if __name__ == '__main__':
    main()
