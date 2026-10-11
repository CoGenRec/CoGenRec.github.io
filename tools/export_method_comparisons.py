#!/usr/bin/env python3
"""Export official-checkpoint comparisons and matching F0 deblurring images.

Existing NPZs are the only image sources. Video panels share one media clock;
selected AOPs are held for their actual acquisition intervals. STGDNet is used
only at its cached F0 endpoint. No inference or calibration is performed.
"""

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from export_selected_scenes import PAGE, sha256
from export_rotation_scenes import RUN, SCENES as ROTATION_SCENES, AOPS, RATIO, SOURCE_FPS
from rgb_alignment import rgb_reference

SCENES = {
    key: {**spec, 'last_cop': spec['first_cop']+1,
          'tags': ['Fast motion', 'Blur']}
    for key, spec in ROTATION_SCENES.items()
}
SCENES.update({
    'hdr-cartoon': {
        'source_scene': 'HDR卡通人', 'title': 'Cartoon poster',
        'worker': 3, 'row': 3, 'first_cop': 185, 'last_cop': 185,
        'slug': 'hdr-cartoon-cop185', 'tags': ['HDR'],
    },
    'hdr-bank': {
        'source_scene': 'HDR建行', 'title': 'Sunlit facade',
        'worker': 1, 'row': 1, 'first_cop': 186, 'last_cop': 187,
        'slug': 'hdr-bank-cop186-187', 'tags': ['HDR'],
    },
    'motorcycle': {
        'source_scene': '摩托农夫山泉', 'title': 'Passing motorcycle',
        'worker': 3, 'row': 60, 'first_cop': 752, 'last_cop': 754,
        'slug': 'motorcycle-cop752-754', 'tags': ['Fast motion', 'Blur'],
    },
})
SCENES['turntable']['title'] = 'Spinning disc'

METHODS = [
    ('input', 'Input RGB', None, 'Observation'),
    ('unet', 'Tianmouc-UNet', '008_UNet_NATURE_2024_official_weights', 'Official'),
    ('igfnet', 'IGFNet', '005_IGFNet_Nature_Sensors_2026_official_weights', 'Official'),
    ('cbrdm', 'CBRDM', '002_CBRDM_ICCV_2025_official_weights', 'Official'),
    ('ours', 'CoGenRec', '001_Ours_with_exposure_augmentation', 'Ours'),
]
STGD = ('stgdnet', 'STGDNet', '011_STGDNet_CVPR_2026_official_weights', 'Official')
ENDPOINT_METHODS = [*METHODS[:-1], STGD, METHODS[-1]]
ENCODED_FPS = 60
TILE_WIDTH, TILE_HEIGHT = 640, 320
ROIS = {
    'turntable': [225, 50, 210, 210], 'blocks': [210, 40, 190, 240],
    'hdr-cartoon': [180, 10, 340, 225], 'hdr-bank': [150, 0, 280, 210],
    'motorcycle': [0, 40, 400, 280],
}


def encoding_command(out, suffix=''):
    stem = 'comparison' + (f'-{suffix}' if suffix else '')
    color = ['-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p',
             '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']
    return [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
        '-pixel_format', 'rgb24', '-video_size', '3200x320', '-framerate', '60',
        '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '4', '-preset', 'medium',
        '-crf', '15', '-g', '15', '-bf', '0', *color, '-movflags', '+faststart', str(out/f'{stem}.mp4'),
        '-an', '-c:v', 'libvpx-vp9', '-threads', '4', '-row-mt', '1', '-deadline', 'good',
        '-cpu-used', '4', '-b:v', '0', '-crf', '22', '-g', '15', *color, str(out/f'{stem}.webm'),
    ]


def load_comparison(scene):
    spec = SCENES[scene]
    cache = RUN / f"_cache/worker_{spec['worker']:03d}"
    worker_path = RUN / f"_workers/worker_{spec['worker']:03d}/resolved_run.json"
    worker = json.loads(worker_path.read_text())
    assert worker['ratio'] == RATIO and worker['select_aops'] == AOPS
    source_paths = [worker_path]
    for _, _, directory, kind in ENDPOINT_METHODS:
        if directory:
            method = worker['methods'][int(directory[:3])]
            if kind == 'Official':
                assert 'official weights' in method['label'] and method['ckpt_path']
            else:
                assert method['label'] == 'Ours (with exposure augmentation)'
    samples, endpoints = [], []
    previous_end = None
    for interval, cop in enumerate(range(spec['first_cop'], spec['last_cop']+1)):
        stem = f"csv000_row{spec['row']:06d}_cop{cop:06d}.npz"
        reference_path = cache/'reference'/stem
        source_paths.append(reference_path)
        with np.load(reference_path, allow_pickle=False) as reference:
            rgb = reference['rgb_start'].copy()
            if previous_end is not None:
                assert np.array_equal(previous_end, rgb)
            previous_end = reference['rgb_end'].copy()
            rgb_end = previous_end
        predictions = {}
        for key, _, directory, _ in ENDPOINT_METHODS:
            if not directory:
                continue
            path = cache/'methods'/directory/stem
            source_paths.append(path)
            with np.load(path, allow_pickle=False) as prediction:
                frames = prediction['frames'].copy()
            assert frames.shape == (1 if key == 'stgdnet' else 7, 320, 640, 3)
            assert frames.dtype == np.uint8
            predictions[key] = frames
        endpoints.append({'cop': cop, 'aop': 0, 'images': {
            key: rgb if key == 'input' else predictions[key][0] for key, *_ in ENDPOINT_METHODS
        }})
        for index, aop in enumerate(AOPS):
            rgb_key = rgb_reference(aop, 0, RATIO)
            samples.append(({
                'sample': len(samples), 'cop': cop, 'aop': aop,
                'rgb_reference': rgb_key, 'rgb_cop': cop+(rgb_key == 'rgb_end'),
                'tick': interval*RATIO+aop, 'capture_time_seconds': (interval*RATIO+aop)/SOURCE_FPS,
            }, [(rgb if rgb_key == 'rgb_start' else rgb_end) if key == 'input' else predictions[key][index] for key, *_ in METHODS]))
    return samples, endpoints, source_paths, worker


def export(scene):
    spec = SCENES[scene]
    out = PAGE/'assets/comparisons'/spec['slug']
    out.mkdir(parents=True, exist_ok=True)
    samples, endpoints, source_paths, worker = load_comparison(scene)
    duration_ticks = len(endpoints)*RATIO
    for (key, *_), array in zip(METHODS, samples[0][1]):
        Image.fromarray(array).save(out/f'poster-{key}.jpg', quality=95, subsampling=0)
    Image.fromarray(np.concatenate(samples[0][1], axis=1)).save(out/'poster.jpg', quality=95, subsampling=0)
    roi = ROIS[scene]
    x, y, width, height = roi
    endpoint_map = []
    for endpoint in endpoints:
        item = {'cop': endpoint['cop'], 'aop': 0, 'images': {}}
        for key, array in endpoint['images'].items():
            name = f"endpoint-cop{endpoint['cop']}-{key}.png"
            crop_name = f"endpoint-cop{endpoint['cop']}-{key}-crop.png"
            Image.fromarray(array).save(out/name)
            Image.fromarray(array[y:y+height, x:x+width]).save(out/crop_name)
            item['images'][key] = {'image': name, 'crop': crop_name}
        endpoint_map.append(item)
    display_samples = []
    for index, (info, _) in enumerate(samples):
        next_tick = samples[index+1][0]['tick'] if index+1 < len(samples) else duration_ticks
        display_samples.extend([index]*(next_tick-info['tick']))
    assert len(display_samples) == duration_ticks
    previews = {}
    for factor in (1, 2):
        count = int(np.ceil(duration_ticks*ENCODED_FPS*factor/SOURCE_FPS))
        ticks = [min(duration_ticks-1, int(np.floor(i*SOURCE_FPS/(ENCODED_FPS*factor)+.5))) for i in range(count)]
        previews[factor] = {'ticks': ticks, 'data': []}
    encoder = subprocess.Popen(encoding_command(out), stdin=subprocess.PIPE)
    try:
        for tick, sample_index in enumerate(display_samples):
            payload = np.concatenate(samples[sample_index][1], axis=1).tobytes()
            encoder.stdin.write(payload)
            for preview in previews.values():
                if tick in preview['ticks']:
                    preview['data'].append(payload)
    finally:
        encoder.stdin.close()
        code = encoder.wait()
    assert code == 0
    for factor, preview in previews.items():
        process = subprocess.Popen(encoding_command(out, 'original' if factor == 1 else f'slow{factor}'), stdin=subprocess.PIPE)
        try:
            for payload in preview['data']:
                process.stdin.write(payload)
        finally:
            process.stdin.close()
            code = process.wait()
        assert code == 0
    manifest = {
        'title': spec['title'], 'source_scene': spec['source_scene'], 'source_run': str(RUN),
        'nominal_source_fps': SOURCE_FPS, 'ratio': RATIO, 'select_aops': AOPS,
        'cop_range_inclusive': [spec['first_cop'], spec['last_cop']],
        'source_sample_count': len(samples), 'samples': [info for info, _ in samples],
        'sample_ticks': [info['tick'] for info, _ in samples],
        'duration_ticks': duration_ticks, 'encoded_frame_count': duration_ticks,
        'encoded_fps': ENCODED_FPS, 'capture_duration_seconds': duration_ticks/SOURCE_FPS,
        'tile_size': [TILE_WIDTH, TILE_HEIGHT], 'video_size': [3200, 320],
        'video_methods': [{'key': key, 'label': label, 'cache_directory': directory, 'kind': kind} for key, label, directory, kind in METHODS],
        'endpoint_methods': [{'key': key, 'label': label, 'cache_directory': directory, 'kind': kind} for key, label, directory, kind in ENDPOINT_METHODS],
        'checkpoint_provenance': {key: worker['methods'][int(directory[:3])] for key, _, directory, _ in ENDPOINT_METHODS if directory},
        'synchronization': 'All five method panels baked into one video; canvases render corresponding tiles from that same decoded frame',
        'timeline_policy': 'Hold each retained AOP until the next; no inferred intermediate frames',
        'rgb_policy': 'First half of each COP interval uses rgb_start; second half uses rgb_end; exact midpoint uses rgb_start',
        'rgb_switch_aop': RATIO//2+1,
        'encoded_frames': [{'frame': tick, 'source_sample': index} for tick, index in enumerate(display_samples)],
        'fast_previews': {str(f): {'encoded_ticks': p['ticks'], 'source_samples': [display_samples[t] for t in p['ticks']], 'frame_count': len(p['ticks'])} for f, p in previews.items()},
        'endpoint_policy': 'F0 at AOP 0 of each selected COP; STGDNet frames[0] is used only here',
        'endpoint_images': endpoint_map, 'detail_roi_xywh': roi,
        'sources': [{'path': str(path), 'sha256': sha256(path)} for path in source_paths],
    }
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'scene': scene, 'video_methods': len(METHODS), 'endpoints': len(endpoints), 'endpoint_methods': len(ENDPOINT_METHODS), 'samples': len(samples)}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenes', choices=(*SCENES, 'all'), nargs='+')
    args = parser.parse_args()
    for scene in SCENES:
        if scene in args.scenes or 'all' in args.scenes:
            export(scene)


if __name__ == '__main__':
    main()
