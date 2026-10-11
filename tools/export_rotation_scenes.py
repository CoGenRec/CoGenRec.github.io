#!/usr/bin/env python3
"""Export two rotation scenes from their existing seven-AOP comparison caches.

Preserves actual capture spacing by holding each retained sample until the next
one. Repeated display frames are not new reconstructions; frame stepping exposes
only the 14 retained samples. No inference or calibration is performed.
"""

import argparse
import json

import numpy as np

from export_selected_scenes import REPO, export_scene, sha256

RUN = REPO / 'output/real_tmrec_offical_weights_and_retrain_weights_three_variants'
METHOD = '001_Ours_with_exposure_augmentation'
AOPS = [0, 4, 8, 12, 16, 20, 24]
RATIO = 25
SOURCE_FPS = 757
SAMPLE_TICKS = AOPS + [RATIO + aop for aop in AOPS]
SCENES = {
    'turntable': {
        'source_scene': '大HW转盘', 'title': 'HW turntable',
        'worker': 2, 'row': 89, 'first_cop': 2,
        'slug': 'hw-turntable-cop2-3', 'poster_frame': 12,
    },
    'blocks': {
        'source_scene': '旋转积木', 'title': 'Rotating blocks',
        'worker': 1, 'row': 56, 'first_cop': 40,
        'slug': 'rotating-blocks-cop40-41', 'poster_frame': 16,
    },
}


def source_paths(scene):
    spec = SCENES[scene]
    cache = RUN / f"_cache/worker_{spec['worker']:03d}"
    result = []
    for cop in range(spec['first_cop'], spec['first_cop'] + 2):
        stem = f"csv000_row{spec['row']:06d}_cop{cop:06d}.npz"
        result.extend([cache / 'reference' / stem, cache / 'methods' / METHOD / stem])
    return result


def rotation_samples(scene):
    spec = SCENES[scene]
    manifest_path = RUN / f"_workers/worker_{spec['worker']:03d}/resolved_run.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest['select_aops'] == AOPS and manifest['ratio'] == RATIO
    assert manifest['methods'][1]['label'] == 'Ours (with exposure augmentation)'
    previous_end = None
    paths = source_paths(scene)
    for interval in range(2):
        cop = spec['first_cop'] + interval
        with np.load(paths[2 * interval], allow_pickle=False) as ref, np.load(
            paths[2 * interval + 1], allow_pickle=False
        ) as prediction:
            for array in (ref['td'], ref['sd'], prediction['frames']):
                assert array.shape == (7, 320, 640, 3) and array.dtype == np.uint8
            if previous_end is not None:
                assert np.array_equal(previous_end, ref['rgb_start'])
            previous_end = ref['rgb_end'].copy()
            for index, aop in enumerate(AOPS):
                sample = interval * len(AOPS) + index
                tick = interval * RATIO + aop
                yield {
                    'cop': cop, 'aop': aop, 'source_sample_index': sample,
                    'source_sample_tick': tick,
                    'source_sample_time_seconds': tick / SOURCE_FPS,
                    'source_scene_video_frame': 7 + sample,
                }, (ref['rgb_start'], ref['td'][index], ref['sd'][index], prediction['frames'][index])


def rotation_frames(scene):
    samples = list(rotation_samples(scene))
    for index, (info, arrays) in enumerate(samples):
        next_tick = SAMPLE_TICKS[index + 1] if index + 1 < len(samples) else 2 * RATIO
        for tick in range(info['source_sample_tick'], next_tick):
            yield {**info, 'held_display_tick': tick}, arrays


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', choices=(*SCENES, 'all'), nargs='?', default='all')
    args = parser.parse_args()
    for scene, spec in SCENES.items():
        if args.scene not in (scene, 'all'):
            continue
        worker_manifest = RUN / f"_workers/worker_{spec['worker']:03d}/resolved_run.json"
        source_video = RUN / 'scenes' / f"{spec['source_scene']}.mp4"
        samples = [info for info, _ in rotation_samples(scene)]
        export_scene(spec['slug'], spec['title'], SOURCE_FPS, 2 * RATIO,
                     lambda scene=scene: rotation_frames(scene), [1, 2], spec['poster_frame'], 0, {
                         'source_run': str(RUN), 'source_scene': spec['source_scene'],
                         'source_video': str(source_video), 'source_video_sha256': sha256(source_video),
                         'worker_manifest': str(worker_manifest), 'worker_manifest_sha256': sha256(worker_manifest),
                         'method': METHOD, 'method_label': 'Ours (with exposure augmentation)',
                         'ratio': RATIO, 'cop_range_inclusive': [spec['first_cop'], spec['first_cop'] + 1],
                         'select_aops': AOPS, 'source_sample_count': len(samples),
                         'source_samples': samples, 'sample_ticks': SAMPLE_TICKS,
                         'duration_ticks': 2 * RATIO,
                         'rate_basis': '757 FPS capture mode; source run retains only seven selected AOPs per COP',
                         'timeline_policy': 'Hold the previous retained sample until the next real AOP; no synthesized intermediate samples',
                         'capture_time_semantics': 'frames.capture_time_seconds is the held display tick; source_sample_time_seconds is the actual retained sample timestamp',
                         'rgb_policy': 'Hold rgb_start for each COP; no AOP 25 endpoint is retained in this run',
                         'endpoint_policy': 'All cached AOP 0,4,8,12,16,20,24 in both selected COP intervals',
                         'sources': [{'path': str(path), 'sha256': sha256(path)} for path in source_paths(scene)],
                     })


if __name__ == '__main__':
    main()
