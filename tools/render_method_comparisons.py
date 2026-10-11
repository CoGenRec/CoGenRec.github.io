#!/usr/bin/env python3
"""Refresh only the comparison section from exported scene manifests."""

from html import escape
import json

from export_method_comparisons import PAGE, SCENES, METHODS, ENDPOINT_METHODS


def method_name(label, kind):
    qualifier = '<span class="method-kind">Official weights</span>' if kind == 'Official' else ''
    return f'<figcaption class="method-name">{escape(label)}{qualifier}</figcaption>'


def video_method(method, index, base):
    key, label, _, kind = method
    return f'''<figure class="comparison-method{' ours' if key == 'ours' else ''}">
                  {method_name(label, kind)}
                  <img class="method-poster" src="{base}/poster-{key}.jpg" alt="{escape(label)} comparison preview" width="640" height="320" loading="lazy">
                  <canvas data-method-tile="{index}" width="640" height="320" role="img" aria-label="{escape(label)}" hidden></canvas>
                </figure>'''


def endpoint_method(method, base, cop):
    key, label, _, kind = method
    return f'''<figure class="comparison-method{' ours' if key == 'ours' else ''}">
                  {method_name(label, kind)}
                  <img src="{base}/endpoint-cop{cop}-{key}.png" alt="{escape(label)}" width="640" height="320" loading="lazy" decoding="async">
                </figure>'''


def scene_article(scene):
    spec = SCENES[scene]
    base = 'assets/comparisons/' + spec['slug']
    manifest = json.loads((PAGE/base/'manifest.json').read_text())
    first = manifest['cop_range_inclusive'][0]
    video = '\n                '.join(video_method(method, i, base) for i, method in enumerate(METHODS))
    endpoint = '\n                '.join(endpoint_method(method, base, first) for method in ENDPOINT_METHODS)
    tags = ''.join(f'<li class="scene-tag">{escape(tag)}</li>' for tag in spec['tags'])
    ticks = ','.join(map(str, manifest['sample_ticks']))
    return f'''        <article class="comparison-scene" data-comparison-scene="{scene}" id="comparison-{scene}">
          <header class="comparison-scene-heading">
            <h3>{escape(spec['title'])}</h3>
            <ul class="scene-tags" aria-label="Scene tags"><li class="scene-tag frame-rate">{manifest['nominal_source_fps']} FPS</li>{tags}</ul>
          </header>
          <div data-comparison-panel="video">
            <div class="sync-player comparison-player" data-clock="media-time" data-source-fps="{manifest['nominal_source_fps']}" data-encoded-fps="{manifest['encoded_fps']}" data-frame-count="{manifest['source_sample_count']}" data-ratio="{manifest['ratio']}" data-first-cop="{first}" data-sample-ticks="{ticks}" data-duration-ticks="{manifest['duration_ticks']}">
              <video autoplay muted loop playsinline preload="none" aria-hidden="true" tabindex="-1">
                <source src="{base}/comparison.mp4" type="video/mp4; codecs=avc1.640028">
                <source src="{base}/comparison.webm" type="video/webm; codecs=vp9">
              </video>
              <div class="comparison-method-grid">
                {video}
              </div>
            </div>
          </div>
          <div class="comparison-endpoint-panel" data-comparison-panel="deblur" hidden>
            <div class="comparison-method-grid comparison-endpoint-grid">
                {endpoint}
            </div>
          </div>
        </article>'''


def render():
    articles = '\n'.join(scene_article(scene) for scene in SCENES)
    section = '''    <section class="container section" id="comparisons" aria-labelledby="comparisons-title">
      <div class="section-heading">
        <h2 id="comparisons-title">Method comparisons</h2>
        <div class="task-picker" role="group" aria-label="Comparison task"><button class="task-button" type="button" data-task="video" aria-pressed="true">Video reconstruction</button><button class="task-button" type="button" data-task="deblur" aria-pressed="false">RGB deblurring</button></div>
      </div>
      <div class="comparison-list">
''' + articles + '''
      </div>
    </section>

'''
    path = PAGE/'index.html'
    html = path.read_text()
    start = html.index('    <section class="container section" id="comparisons"')
    end = html.index('    <section class="container section resources-section"', start)
    path.write_text(html[:start]+section+html[end:])
    print(f'Rendered {len(SCENES)} comparison scenes.')


if __name__ == '__main__':
    render()
