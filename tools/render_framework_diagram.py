#!/usr/bin/env python3
"""Render self-contained SVG architecture diagrams with a shared input timeline.

COP58 supplies the native measurement and reconstruction thumbnails. TD and SD
are horizontally mirrored for display; RGB and prediction pixels are unchanged.
All geometry, typography and animation are vector graphics.
"""

import base64
import hashlib
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageOps

PAGE = Path(__file__).resolve().parents[1]
OUT = PAGE / 'assets/framework'
RUN = PAGE.parent / 'output/real_tmrec_varlen_oursdecoder_iter010000_waterball2_cop058_059_gpu6'
INPUTS = RUN / 'input_frames/cop000058'
PREDICTION = RUN / '_cache/methods/000_VarLen_OursDecoder_iter_010000/csv000_row000000_cop000058.npz'
METHOD_REFERENCE = Path('/data2/myp/overleaf_projects/Tianmouc-HS-HDR-Deblur-Submitted-to-PAMI-/sec/3_method.tex')

# The same piecewise-linear time mapping is used by every measurement row.
# Times 3..22 are omitted, rather than drawn with misleading thumbnail overlap.
SD_TIMES = (0, 1, 2, 23, 24, 25)
TD_STARTS = (0, 1, 23, 24)
TIME_X = dict(zip(SD_TIMES, (300, 364, 428, 532, 596, 660)))
TIME_STEP = 64
MEASUREMENTS_WIDTH = 800

STYLE = '''
.framework-svg text { font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; fill: #172435; font-size: 20px; }
.framework-svg .heading { font-size: 24px; font-weight: 650; }
.framework-svg .subheading { font-size: 21px; font-weight: 600; }
.framework-svg .small { font-size: 17px; fill: #536477; }
.framework-svg .micro { font-size: 15px; fill: #536477; }
.framework-svg .math { font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-size: 22px; }
.framework-svg .numeric-index { font-family: Arial, Helvetica, sans-serif; font-style: normal; font-weight: 600; font-variant-numeric: lining-nums tabular-nums; }
.framework-svg .blue { fill: #234e98; }
.framework-svg .warm { fill: #92501f; }
.framework-svg .module { fill: #fbe6d3; stroke: #a65b28; stroke-width: 1.7; }
.framework-svg .block { fill: #f5c39c; stroke: #a65b28; stroke-width: 1.7; }
.framework-svg .label { paint-order: stroke; stroke: white; stroke-width: 5px; stroke-linejoin: round; }
.framework-svg .edge { fill: none; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.framework-svg .scan { animation: scan-time 5.8s linear infinite; pointer-events: none; }
.framework-svg.architecture text { font-weight: 600; }
.framework-svg.architecture .heading, .framework-svg.architecture .subheading { font-weight: 650; }
.framework-svg.architecture .module-label { font-weight: 600; }
.framework-svg.architecture .math { font-weight: 550; }
.framework-svg.architecture .small, .framework-svg.architecture .micro { font-weight: 500; }
.framework-svg .diagram-group { --focus-color: #648ac3; --focus-tint: #eef4fc; }
.framework-svg .diagram-group.warm-focus { --focus-color: #ae652e; --focus-tint: #fff0df; }
.framework-svg [data-hotspot] { cursor: pointer; outline: none; }
.framework-svg .focus-surface, .framework-svg .thumbnail { transition: fill .18s ease, stroke .18s ease, stroke-width .18s ease, filter .18s ease; }
.framework-svg .focus-band { fill: var(--focus-tint); stroke: var(--focus-color); stroke-width: 1.6; opacity: 0; pointer-events: none; transition: opacity .18s ease; }
.framework-svg .diagram-group.is-highlighted > .focus-surface { fill: var(--focus-tint); stroke: var(--focus-color); stroke-width: 2.5; filter: drop-shadow(0 2px 3px rgb(38 64 100 / .16)); }
.framework-svg .diagram-group.is-highlighted > .focus-band { opacity: .8; }
.framework-svg .diagram-group.is-highlighted .thumbnail { stroke: var(--focus-color); stroke-width: 2.4; filter: drop-shadow(0 2px 3px rgb(38 64 100 / .22)); }
.framework-svg .endpoint-frame { fill: var(--focus-tint); stroke: var(--focus-color); stroke-width: 2.5; opacity: 0; pointer-events: none; transition: opacity .18s ease; }
.framework-svg .exposure-window { transition: fill .18s ease, stroke .18s ease; }
.framework-svg .diagram-group.is-highlighted > .endpoint-frame { opacity: 1; filter: drop-shadow(0 2px 3px rgb(38 64 100 / .16)); }
.framework-svg .diagram-group.is-highlighted > .exposure-window { fill: transparent; stroke: transparent; }
.framework-svg[data-framework-panel="measurements"] .diagram-group[data-highlight^="endpoint-"].is-highlighted .thumbnail { stroke: #d4dfea; stroke-width: 1; filter: none; }
@keyframes scan-time { 0% { transform: translateX(0); opacity: 0; } 8% { opacity: .7; } 92% { opacity: .7; } 100% { transform: translateX(360px); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .framework-svg .scan { display: none; animation: none; } .framework-svg .focus-surface, .framework-svg .thumbnail, .framework-svg .focus-band, .framework-svg .endpoint-frame, .framework-svg .exposure-window { transition: none; } }
'''
STATIC_STYLE = '.framework-static .scan { display: none !important; animation: none !important; }'


def text(x, y, content, cls='', anchor='start', size=None):
    size = f' style="font-size:{size}px"' if size else ''
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{size}>{escape(content)}</text>'


def lines(x, y, values, cls='', anchor='middle', step=25, size=None):
    return ''.join(text(x, y + i * step, value, cls, anchor, size) for i, value in enumerate(values))


def math(x, y, base, sub='', sup='', anchor='start', size=22):
    def index_markup(value):
        return ''.join(f'<tspan class="numeric-index">{part}</tspan>' if part.isdecimal()
                       else escape(part) for part in re.split(r'(\d+)', value))

    sub_size = '75%' if sub.isdecimal() else '65%'
    return (f'<text x="{x}" y="{y}" class="math" text-anchor="{anchor}" style="font-size:{size}px">'
            f'{escape(base)}<tspan baseline-shift="sub" font-size="{sub_size}">{index_markup(sub)}</tspan>'
            f'<tspan baseline-shift="super" font-size="65%">{index_markup(sup)}</tspan></text>')


def rect(x, y, w, h, fill='#fff', stroke='#e0e6eb', radius=12, cls=''):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" class="{cls}"/>'


def detail_fusion_label(x, y, size=20):
    return (f'<text x="{x}" y="{y}" class="math" text-anchor="middle" '
            f'data-detail-formula="" style="font-size:{size}px">'
            '<tspan font-style="normal">Ψ(</tspan>V'
            '<tspan baseline-shift="sub" font-size="65%" font-style="normal">ctrl</tspan>'
            '<tspan baseline-shift="super" font-size="65%">'
            '<tspan class="numeric-index">0</tspan>,…,T−'
            '<tspan class="numeric-index">1</tspan></tspan>'
            '<tspan font-style="normal">)</tspan></text>')


def arrow(d, prefix, blue=False):
    color = '#547db8' if blue else '#b8692c'
    marker = f'{prefix}-arrow-{"blue" if blue else "warm"}'
    return f'<path d="{d}" class="edge" stroke="{color}" marker-end="url(#{marker})"/>'


def image(name, x, y, w, h, images):
    return (rect(x, y, w, h, '#142333', '#d4dfea', 3, cls='thumbnail')
            + f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{images[name]}" preserveAspectRatio="xMidYMid meet"/>')


def linked(body, key, label=None, warm=False):
    trigger = (f' data-hotspot="{key}" tabindex="0" role="button" aria-pressed="false" '
               f'aria-label="{escape(label, quote=True)}"') if label else ''
    return (f'<g class="diagram-group{" warm-focus" if warm else ""}" data-highlight="{key}"{trigger}>'
            + body + '</g>')


def document(prefix, width, height, title, desc, body):
    markers = ''.join(f'<marker id="{prefix}-arrow-{kind}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1 L9 5 L1 9 Z" fill="{color}"/></marker>'
                      for kind, color in [('blue', '#547db8'), ('warm', '#b8692c')])
    architecture = ' architecture' if prefix != 'measurements' else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="framework-svg{architecture}" data-framework-panel="{prefix}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{prefix}-title {prefix}-desc">'
            f'<title id="{prefix}-title">{escape(title)}</title><desc id="{prefix}-desc">{escape(desc)}</desc>'
            f'<style>{STYLE}</style><defs>{markers}</defs>{body}</svg>')


def measurements(images):
    p = 'measurements'
    b = rect(1, 1, MEASUREMENTS_WIDTH-2, 748, '#fff', '#cbd9ec', 16)
    b += text(22, 34, 'Input · Dual-pathway CVS', 'heading blue')
    b += text(30, 82, 'Cognition-oriented pathway (COP)', 'subheading blue')

    # Exposure windows and all sampling rows share exactly the same x mapping.
    # The exposure contains three AOP periods and two valid TD intervals.
    for endpoint, t in ((0, 0), (1, 25)):
        x = TIME_X[t]
        b += f'<g class="diagram-group" data-highlight="endpoint-{endpoint}" data-exposure="{endpoint}" data-center-time="{t}" data-duration="3">'
        # A single hover frame spans RGB and its intra-exposure measurements.
        # The neutral exposure backdrop recedes while this frame is active.
        b += rect(x-112, 106, 224, 358, radius=10, cls='endpoint-frame')
        exposure_half_width = 1.5 * TIME_STEP
        b += rect(x-exposure_half_width, 229, 2*exposure_half_width, 235, '#f5f7f8', '#e6ebef', 9, cls='exposure-window')
        b += f'<path d="M{x-exposure_half_width} 231 V239 H{x+exposure_half_width} V231" fill="none" stroke="#547db8" stroke-width="1.5"/>'
        b += math(x, 261, 'τ', 'COP', anchor='middle', size=20)
        b += f'<path d="M{x} 224 V692" stroke="#7799c7" stroke-dasharray="4 5" stroke-width="1.2"/>'
        # The RGB label forms a legend in the continuous frame's top edge.
        b += rect(x-44, 88, 88, 34, '#fff', 'none', 0)
        b += math(x, 110, 'RGB', str(endpoint), anchor='middle', size=24)
        b += image(f'rgb{endpoint}', x-100, 124, 200, 100, images)
        b += '</g>'

    for t in (1, 2, 23, 24):
        x = TIME_X[t]
        b += f'<path d="M{x} 520 V692" stroke="#c0d0e4" stroke-dasharray="3 5" stroke-width="1"/>'
    # One label column serves both AOP sections. Endpoint frames occupy the
    # measurement columns, leaving the headings and row labels unobstructed.
    b += lines(30, 256, ['Action-oriented', 'pathway (AOP)'], 'subheading blue', anchor='start', step=23, size=19)
    b += text(30, 318, 'Intra-exposure', 'small', size=19)
    b += math(30, 361, 'TD', sup='in', size=23)
    b += math(30, 431, 'SD', sup='in', size=23)

    def interval(x0, x1, y):
        # A capped span represents a change over an interval, not an instant.
        return (f'<path d="M{x0} {y-4} V{y+4} M{x0} {y} H{x1} M{x1} {y-4} V{y+4}" '
                'fill="none" stroke="#547db8" stroke-width="1.8"/>')

    def sample(x, image_bottom, y):
        return (f'<path d="M{x} {image_bottom} V{y}" stroke="#547db8" stroke-width="1.3"/>'
                f'<circle cx="{x}" cy="{y}" r="3.5" fill="#315f9f"/>')

    for endpoint, t in ((0, 0), (1, 25)):
        x = TIME_X[t]
        for j, start in enumerate((-1, 0)):
            center = x + (start+.5)*TIME_STEP
            b += f'<g class="diagram-group" data-highlight="endpoint-{endpoint}" data-signal="td-in" data-endpoint="{endpoint}" data-start-time="{t+start}" data-end-time="{t+start+1}">'
            b += image(f'td_in{endpoint}{j}', center-30, 338, 60, 30, images)
            b += f'<path d="M{center} 368 V382" stroke="#547db8"/>'
            b += interval(x+start*TIME_STEP, x+(start+1)*TIME_STEP, 382)
            b += '</g>'
        b += f'<g class="diagram-group" data-highlight="endpoint-{endpoint}" data-signal="sd-in" data-endpoint="{endpoint}" data-time="{t}" data-channel="0">'
        b += image(f'sd_in{endpoint}', x-30, 408, 60, 30, images)
        b += sample(x, 438, 453) + '</g>'

    b += '<path d="M24 478 H776" stroke="#e1e8f1"/>'
    b += '<g class="diagram-group" data-highlight="between">'
    b += rect(24, 486, 752, 178, radius=9, cls='focus-band')
    b += text(30, 508, 'Inter-exposure', 'small', size=19)
    b += math(30, 551, 'TD', sup='btw', size=23)
    b += math(30, 621, 'SD', sup='btw', size=23)
    for t in TD_STARTS:
        x0, x1 = TIME_X[t], TIME_X[t+1]
        center = (x0+x1)/2
        b += f'<g data-signal="td-between" data-start-time="{t}" data-end-time="{t+1}" data-source-frame="{t+1}">'
        b += image(f'td_btw{t+1}', center-30, 528, 60, 30, images)
        b += f'<path d="M{center} 558 V572" stroke="#547db8"/>'
        b += interval(x0, x1, 572) + '</g>'
    for t in SD_TIMES:
        x = TIME_X[t]
        b += f'<g data-signal="sd-between" data-time="{t}" data-channel="0">'
        b += image(f'sd_btw{t}', x-30, 598, 60, 30, images)
        b += sample(x, 628, 643) + '</g>'
    # Ellipses and an explicit axis break use the same omitted middle interval.
    b += text(480, 551, '…', 'blue', 'middle', 24)
    b += text(480, 621, '…', 'blue', 'middle', 24)
    b += '</g>'
    b += '<path d="M210 684 H461 M476 677 L470 691 M491 677 L485 691" fill="none" stroke="#547db8" stroke-width="1.7"/>'
    b += arrow('M504 684 H766', p, blue=True)
    for t, label in ((0, '0'), (1, '1'), (2, '2'), (23, 'T−3'), (24, 'T−2'), (25, 'T−1')):
        x = TIME_X[t]
        b += f'<path d="M{x} 679 V690" stroke="#547db8" stroke-width="1.7"/>'
        b += math(x, 713, 't', label, anchor='middle', size=19)
    b += '<g transform="translate(300 124)"><g class="scan"><rect width="2" height="568" fill="#90b7ff"/><rect width="10" height="568" fill="#90b7ff" opacity=".10"/></g></g>'
    return document(p, MEASUREMENTS_WIDTH, 750, 'COP and AOP measurement timing',
                    'RGB0 and RGB1 exposure windows are centered at t0 and t25. Each exposure contains two valid TD intervals and one SD midpoint sample. Inter-exposure SD samples align with sampling instants; TD images span adjacent instants. All TD and SD images are horizontally mirrored. Middle times are omitted for readability. A moving scan extends through the RGB, intra-exposure and inter-exposure rows.', b)


def endpoint_input(x, y, endpoint, w=94, h=88):
    b = rect(x, y, w, h, '#fff7ee', '#dbb18b', 8, cls='focus-surface')
    b += math(x + w / 2, y + 25, 'RGB', str(endpoint), anchor='middle', size=20)
    b += math(x + w / 2, y + 51, 'TD', str(endpoint), 'in', anchor='middle', size=19)
    b += math(x + w / 2, y + 76, 'SD', str(endpoint), 'in', anchor='middle', size=19)
    return linked(b, f'endpoint-{endpoint}', f'Highlight RGB{endpoint} and its intra-exposure TD and SD')


def reconstruction(images, mobile=False):
    p = 'reconstruction-mobile' if mobile else 'reconstruction'
    if mobile:
        b = rect(1, 1, 558, 808, '#fffdfb', '#e3cbb4', 16)
        b += text(22, 35, 'CoGenRec · Reconstruction', 'heading warm')
        for endpoint, x in [(0, 22), (1, 314)]:
            b += endpoint_input(x, 64, endpoint, 224)
            b += arrow(f'M{x+112} 153 V171', p)
            b += linked(rect(x, 175, 224, 74, cls='module focus-surface')
                        + lines(x+112, 204, ['Exposure-Aware', 'Endpoint Encoder'], size=21),
                        'encoder', 'Highlight both endpoint encoders and their detailed architecture', warm=True)
            b += arrow(f'M{x+112} 249 V264 H{200 if endpoint == 0 else 360} V284', p)
        b += linked(rect(130, 288, 300, 88, cls='module focus-surface')
                    + lines(280, 324, ['Bi-Directional Recurrent', 'Temporal Propagator'], size=22),
                    'propagator', 'Highlight the temporal propagator and its detailed architecture', warm=True)
        b += linked(rect(22, 299, 82, 66, '#fff7ee', '#dbb18b', 8, cls='focus-surface')
                    + math(63, 326, 'SD', sup='btw', anchor='middle', size=19)
                    + math(63, 352, 'TD', sup='btw', anchor='middle', size=19),
                    'between', 'Highlight inter-exposure TD and SD')
        b += arrow('M104 332 H128', p)
        b += arrow('M210 377 V401 H133 V425', p)
        b += arrow('M350 377 V401 H425 V425', p)
        b += rect(28, 429, 210, 74, cls='module') + text(133, 471, 'ControlNet', 'module-label', 'middle', 22)
        b += rect(330, 429, 190, 74, cls='module')
        b += text(425, 456, 'Detail Fusion', 'module-label', 'middle', 19)
        b += detail_fusion_label(425, 486)
        b += arrow('M133 505 V542', p) + arrow('M425 505 V542', p)
        b += rect(28, 546, 242, 98, cls='module')
        b += lines(149, 590, ['Stable Diffusion', 'Video Backbone'], size=22)
        b += rect(326, 546, 194, 98, cls='module')
        b += lines(423, 590, ['VAE', 'Decoder'], size=23)
        b += arrow('M272 597 H323', p)
        b += arrow('M423 646 V674 H231 V697', p)
        b += image('pred0', 101, 711, 112, 56, images) + image('pred1', 249, 711, 112, 56, images)
        b += text(231, 803, 'Predicted RGB Video', 'subheading', 'middle', 21)
        b += text(231, 747, '…', 'small', 'middle', 25)
        return document(p, 560, 810, 'CoGenRec reconstruction pipeline',
                        'Two exposure-aware endpoint encoders and inter-exposure measurements feed the bidirectional temporal propagator. Its features condition ControlNet and detail fusion. The diffusion backbone and VAE decoder produce RGB video.', b)

    b = rect(1, 1, 998, 408, '#fffdfb', '#e3cbb4', 16)
    b += text(22, 35, 'CoGenRec · Complementarity-Driven Reconstruction', 'heading warm')
    for endpoint, y in [(0, 74), (1, 266)]:
        b += endpoint_input(22, y, endpoint)
        b += arrow(f'M118 {y+44} H139', p)
        b += linked(f'<path d="M144 {y+2} L310 {y+16} V{y+72} L144 {y+86} Z" class="module focus-surface"/>'
                    + lines(227, y+36, ['Exposure-Aware', 'Endpoint Encoder'], step=23, size=17.5),
                    'encoder', 'Highlight both endpoint encoders and their detailed architecture', warm=True)
        b += arrow(f'M313 {y+44} H324', p)
    b += linked(rect(22, 185, 94, 59, '#fff7ee', '#dbb18b', 8, cls='focus-surface')
                + math(69, 209, 'SD', sup='btw', anchor='middle', size=19)
                + math(69, 234, 'TD', sup='btw', anchor='middle', size=19),
                'between', 'Highlight inter-exposure TD and SD')
    b += arrow('M119 205 H324', p) + arrow('M119 230 H324', p)
    b += linked(rect(328, 76, 148, 278, cls='module focus-surface')
                + lines(402, 181, ['Bi-Directional', 'Recurrent', 'Temporal', 'Propagator'], step=27, size=20),
                'propagator', 'Highlight the temporal propagator and its detailed architecture', warm=True)
    b += arrow('M478 120 H509', p)
    b += '<path d="M514 83 L656 100 V146 L514 164 Z" class="module"/>'
    b += text(585, 130, 'ControlNet', 'module-label', 'middle', 20)
    for x in (548, 585, 622):
        b += arrow(f'M{x} 166 V222', p)
    b += '<path d="M512 226 L594 244 L680 226 V344 L594 326 L512 344 Z" class="module"/>'
    b += lines(596, 281, ['Stable Diffusion', 'Video Backbone'], step=25, size=20)
    b += arrow('M682 284 H719', p)
    b += '<path d="M724 247 L850 226 V344 L724 323 Z" class="module"/>'
    b += lines(788, 281, ['VAE', 'Decoder'], step=26, size=22)
    b += text(788, 76, 'Detail Fusion', 'subheading', 'middle', 19)
    b += detail_fusion_label(788, 107)
    feature_y, feature_bottom = 152, 181
    for i, x in enumerate((743, 769, 795, 821)):
        b += rect(x, feature_y-i*8, 13, 29+i*8, cls='block detail-feature', radius=2)
        b += arrow(f'M{x+6.5} {feature_bottom+10} V{234-(i*4)}', p)
    # The horizontal guide meets the first feature at its vertical center.
    b += arrow(f'M402 356 V377 H704 V{feature_y+29/2} H739', p)
    b += text(543, 398, 'Multi-Scale Spatio-Temporal Guidance', 'small warm', 'middle', 17)
    b += arrow('M852 284 H880', p)
    b += image('pred0', 886, 151, 94, 47, images) + image('pred1', 886, 269, 94, 47, images)
    b += text(933, 236, '…', 'small', 'middle', 25)
    b += lines(933, 357, ['Predicted', 'RGB Video'], step=23, size=18)
    return document(p, 1000, 410, 'CoGenRec reconstruction pipeline',
                    'The two exposure-aware endpoint encoders and between-exposure TD/SD feed the bidirectional recurrent temporal propagator. Multi-scale features guide ControlNet and detail fusion. Stable Diffusion and the VAE decoder reconstruct RGB video.', b)


def endpoint_encoder():
    p = 'endpoint-encoder'
    b = rect(1, 1, 478, 318, '#fff', '#e3cbb4', 14, cls='focus-surface')
    b += text(20, 34, 'Exposure-Aware Endpoint Encoder', 'subheading warm', size=22)
    # The named fusion region owns both modality input ports and the fused RGB
    # hierarchy. Its boundary hides no crossing wires: TD/SD enter the region,
    # while the four RGB feature outputs have a separate internal routing lane.
    b += '<g data-encoder-fusion="">'
    b += rect(114, 118, 272, 120, '#fff3e6', '#d5a77f', 10, cls='fusion-region')
    b += text(250, 146, 'Cross-Attention Fusion', 'subheading warm', 'middle', 18)
    for x, h in ((158, 44), (260, 32), (360, 24)):
        b += arrow(f'M{x} {83+h/2} V116', p)
        b += arrow(f'M{x} {276-h/2} V240', p)
    b += '</g>'
    for y, name, sup in [(83, 'TD', 'in'), (186, 'RGB', ''), (276, 'SD', 'in')]:
        b += f'<g data-encoder-input="{name}">'
        input_label = rect(14, y-24, 82, 48, '#fff7ee', '#dbb18b', 8,
                           cls='focus-surface encoder-input-label')
        input_label += math(22, y+7, name, '0/1', sup=sup, size=22)
        b += linked(input_label, 'endpoint-inputs',
                    'Highlight the shared TD, RGB and SD inputs for both endpoints')
        b += arrow(f'M104 {y} H137', p)
        for x, w, h in [(140, 36, 44), (240, 40, 32), (340, 40, 24)]:
            b += rect(x, y-h/2, w, h, radius=6, cls='block')
        b += arrow(f'M178 {y} H237', p) + arrow(f'M282 {y} H337', p)
        b += '</g>'
    # Collect the native RGB feature and the three fused encoded RGB scales.
    # Keep these connections and F_end even though the scale glyph is omitted.
    b += '<g data-encoder-output="">'
    for path in ('M110 186 V230 H398', 'M158 208 V225 H398',
                 'M260 202 V220 H398', 'M360 198 V215 H398'):
        b += arrow(path, p)
    b += math(406, 234, 'F', 'end,0/1', size=20)
    b += '</g>'
    b = linked(b, 'encoder', 'Highlight both endpoint encoders and their detailed architecture', warm=True)
    return document(p, 480, 320, 'Exposure-Aware Endpoint Encoder',
                    'TD, RGB and SD inputs each carry the 0/1 endpoint subscript. Three aligned hierarchical branches encode each endpoint. At every encoded scale, TD enters the named Cross-Attention Fusion region from above and SD from below, conditioning the RGB hierarchy inside. The native RGB feature and the three fused encoded RGB features feed F_end,0/1 through a separate output lane below the RGB blocks. The Four Scales caption and stacked feature glyph are omitted.', b)


def temporal_propagator():
    p = 'temporal-propagator'
    b = rect(1, 1, 498, 318, '#fff', '#e3cbb4', 14, cls='focus-surface')
    b += lines(250, 26, ['Bi-Directional Recurrent', 'Temporal Propagator'], 'subheading warm', step=24, size=22)
    b += math(18, 144, 'F', 'end,0', size=18)
    b += math(482, 240, 'F', 'end,1', anchor='end', size=18)

    # The forward and backward streams have separate event inputs. Match the
    # model's f_grus(td[t], sd[t]) and b_grus(td[t+1], sd[t]) indexing.
    # Stagger the two streams around their shared control-volume columns so
    # each post-update state can enter its control volume on a straight line.
    columns = ((124, '0', '1'), (244, '1', '2'), (364, 'T−1', 'T'))
    stagger = 22
    forward_x = [x-stagger for x, _, _ in columns]
    backward_x = [x+stagger for x, _, _ in columns]
    # Recurrent arrows end at each block instead of passing behind the blocks.
    forward_paths = ([f'M75 139 H{forward_x[0]-16}']
                     + [f'M{left+16} 139 H{right-16}' for left, right in zip(forward_x, forward_x[1:])]
                     + [f'M{forward_x[-1]+16} 139 H440'])
    backward_paths = ([f'M424 235 H{backward_x[-1]+16}']
                      + [f'M{right-16} 235 H{left+16}' for left, right in reversed(list(zip(backward_x, backward_x[1:])))]
                      + [f'M{backward_x[0]-16} 235 H58'])
    for direction, paths in (
        ('forward', forward_paths),
        ('backward', backward_paths),
    ):
        b += f'<g data-recurrent-direction="{direction}">'
        b += ''.join(arrow(path, p) for path in paths)
        b += '</g>'

    for x, time, backward_td in columns:
        b += f'<g data-propagator-time="{time}">'
        upper_x, lower_x = x-stagger, x+stagger
        for direction, input_x, y, td_time in (('forward', upper_x, 60, time), ('backward', lower_x, 258, backward_td)):
            input_body = (rect(input_x-43, y, 86, 56, '#fff7ee', '#dbb18b', 7, cls='focus-surface')
                          + math(input_x, y+21, 'TD', td_time, 'btw', anchor='middle', size=17)
                          + math(input_x, y+42, 'SD', time, 'btw', anchor='middle', size=17))
            b += f'<g data-event-direction="{direction}" data-td-index="{td_time}" data-sd-index="{time}">'
            b += linked(input_body, 'between') + '</g>'
        b += arrow(f'M{upper_x} 116 V124', p)
        b += arrow(f'M{lower_x} 258 V250', p)
        b += rect(upper_x-14, 124, 28, 30, radius=5, cls='block')
        b += rect(lower_x-14, 220, 28, 30, radius=5, cls='block')

        # Tap the hidden state AFTER each update: to the right of the forward
        # block and to the left of the backward block. Both enter V_ctrl^t.
        b += f'<g data-control-time="{time}">'
        b += arrow(f'M{x} 139 V168', p)
        b += arrow(f'M{x} 235 V208', p)
        b += rect(x-44, 170, 88, 36, '#fff7ee', '#dbb18b', 7, cls='control-volume')
        b += math(x, 193, 'V', 'ctrl', time, anchor='middle', size=20)
        b += '</g></g>'
    for y in (135, 192, 231):
        b += text(304, y, '…', 'label', 'middle', 25)
    b = linked(b, 'propagator', 'Highlight the temporal propagator and its detailed architecture', warm=True)
    return document(p, 500, 320, 'Bi-Directional Recurrent Temporal Propagator',
                    'The upper stream propagates left to right from the first endpoint using TD_t and SD_t. The lower stream propagates right to left from the second endpoint using TD_(t+1) and SD_t. The streams are horizontally staggered so their post-update hidden states enter each shared central control volume V_ctrl^t through straight vertical arrows. Event inputs sit above the forward stream and below the backward stream.', b)


def load_thumbnails():
    metadata = json.loads((INPUTS / 'metadata.json').read_text())
    assert metadata['cop'] == 58 and metadata['T'] == 26
    assert metadata['select_aops'] == list(range(26))
    assert metadata['cone_exp_period'] == 3
    assert metadata['td_in_exposure_valid_frames'] == 2
    sd_files = sorted((INPUTS / 'sd_between_exposure/channel_0').glob('frame_*.png'))
    td_files = sorted((INPUTS / 'td_between_exposure').glob('frame_*.png'))
    assert len(sd_files) == 26 and len(td_files) == 27
    assert not np.asarray(Image.open(td_files[0])).any()
    assert not np.asarray(Image.open(td_files[-1])).any()

    paths = {f'rgb{i}': INPUTS / f'rgb_endpoints/RGB{i}.png' for i in (0, 1)}
    for i in (0, 1):
        paths[f'sd_in{i}'] = INPUTS / f'sd_in_exposure/RGB{i}/channel_0.png'
        for j in (0, 1):
            paths[f'td_in{i}{j}'] = INPUTS / f'td_in_exposure/RGB{i}/frame_{j:03d}_valid.png'
    paths.update({f'sd_btw{t}': sd_files[t] for t in SD_TIMES})
    # File 1 spans SD0 -> SD1. Files 0 and 26 are zero padding, not samples.
    paths.update({f'td_btw{t+1}': td_files[t+1] for t in TD_STARTS})

    def encoded(panel):
        payload = BytesIO()
        panel.save(payload, format='PNG', optimize=True)
        return 'data:image/png;base64,' + base64.b64encode(payload.getvalue()).decode()

    images, provenance = {}, {}
    for name, path in paths.items():
        panel = Image.open(path).convert('RGB')
        mirrored = name.startswith(('td_', 'sd_'))
        if mirrored:
            panel = ImageOps.mirror(panel)
        images[name] = encoded(panel)
        provenance[name] = {
            'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'transform': 'horizontal mirror' if mirrored else 'none',
        }
    with np.load(PREDICTION) as cache:
        frames = cache['frames']
        assert frames.shape == (26, 320, 640, 3) and frames.dtype == np.uint8
        for name, i in (('pred0', 0), ('pred1', 25)):
            images[name] = encoded(Image.fromarray(frames[i]))
            provenance[name] = {'source': str(PREDICTION), 'frame': i, 'transform': 'none',
                                'sha256': hashlib.sha256(PREDICTION.read_bytes()).hexdigest()}
    return images, provenance, metadata


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images, provenance, metadata = load_thumbnails()

    diagrams = {
        'measurements': measurements(images),
        'reconstruction': reconstruction(images),
        'reconstruction-mobile': reconstruction(images, mobile=True),
        'endpoint-encoder': endpoint_encoder(),
        'temporal-propagator': temporal_propagator(),
    }
    nested = ''
    for name, (x, y, w, h) in {
        'measurements': (0, 0, MEASUREMENTS_WIDTH, 750), 'reconstruction': (820, 0, 1000, 410),
        'endpoint-encoder': (820, 430, 480, 320), 'temporal-propagator': (1320, 430, 500, 320),
    }.items():
        nested += diagrams[name].replace('<svg ', f'<svg x="{x}" y="{y}" width="{w}" height="{h}" ', 1)
    composite = ('<svg xmlns="http://www.w3.org/2000/svg" class="framework-svg framework-composite" viewBox="0 0 1820 750" role="img" aria-labelledby="framework-title framework-desc">'
                 '<title id="framework-title">CoGenRec framework</title>'
                 '<desc id="framework-desc">Dual-pathway CVS measurements, complementarity-driven generative reconstruction, exposure-aware endpoint encoding, and bidirectional recurrent temporal propagation.</desc>'
                 + nested + '</svg>')
    # The desktop reconstruction is embedded in the composite. Only publish
    # the complete desktop figure and the four panels used by narrow layouts.
    published = {name: svg for name, svg in diagrams.items() if name != 'reconstruction'}
    published['cogenrec-framework'] = composite
    # An outer HTML <picture> selects these files for reduced motion. This also
    # works in browsers that do not update media queries inside cached SVG images.
    for name, svg in published.items():
        ET.fromstring(svg)
        (OUT / f'{name}.svg').write_text(svg + '\n')
        static = svg.replace('class="framework-svg', 'class="framework-svg framework-static', 1)
        (OUT / f'{name}-static.svg').write_text(static.replace('</style>', STATIC_STYLE + '</style>') + '\n')
    # SVG images can remain in a browser's memory cache across page reloads.
    # Change their URLs whenever the actual contents change, including the
    # reduced-motion picture sources and the narrow-layout panels.
    versions = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:12]
                for path in sorted(OUT.glob('*.svg'))}
    index_path = PAGE / 'index.html'
    index = index_path.read_text()
    updated_index = re.sub(
        r'assets/framework/([a-z-]+\.svg)(?:\?v=[a-zA-Z0-9_-]+)?',
        lambda match: f'assets/framework/{match[1]}?v={versions[match[1]]}',
        index,
    )
    interaction_version = hashlib.sha256((PAGE / 'framework-interactions.js').read_bytes()).hexdigest()[:12]
    updated_index = re.sub(r'framework-interactions\.js(?:\?v=[a-zA-Z0-9_-]+)?',
                           f'framework-interactions.js?v={interaction_version}', updated_index)
    if updated_index != index:
        index_path.write_text(updated_index)
    (OUT / 'manifest.json').write_text(json.dumps({
        'source_inputs': str(INPUTS), 'cop': 58, 'input_metadata': metadata,
        'raw_inputs_sha256': hashlib.sha256((INPUTS / 'raw_inputs_float32.npz').read_bytes()).hexdigest(),
        'thumbnails': provenance,
        'shared_timeline': {
            'rgb_center_times': [0, 25], 'exposure_duration_aop_periods': 3,
            'sd_channel': 0, 'sd_sample_times': list(range(26)),
            'td_source_indices': list(range(1, 26)), 'excluded_td_padding_indices': [0, 26],
            'td_intervals': [[i, i+1] for i in range(25)],
            'intra_td_offsets_per_endpoint': [[-1, 0], [0, 1]],
            'displayed_sd_times': SD_TIMES, 'displayed_td_start_times': TD_STARTS,
            'omitted_middle_sd_times': list(range(3, 23)),
            'omitted_td_start_times': list(range(2, 23)), 'display_x': TIME_X,
            'axis_break': 'The middle is omitted consistently across all rows; endpoint regions retain equal AOP spacing.',
        },
        'policy': 'TD and SD thumbnails are horizontally mirrored; RGB and predicted RGB are embedded unchanged. Only photographic/sensor thumbnails are raster. Source data and videos are never modified.',
        'animation': 'CSS temporal scanning only; all connection arrows are static and detail features remain solid and opaque; prefers-reduced-motion selects unconditional static variants via HTML picture sources',
        'asset_versions': versions,
        'interaction_script_version': interaction_version,
        'interaction_groups': ['endpoint-0', 'endpoint-1', 'endpoint-inputs', 'between', 'encoder', 'propagator'],
        'temporal_propagator': {
            'implementation_reference': 'CBRDM/TMRGBTSDInterpolation_full.py: BiIterativeTSDInterpolatorFull.forward',
            'forward_inputs': {'td_index': 't', 'sd_index': 't', 'direction': 'left to right'},
            'backward_inputs': {'td_index': 't+1', 'sd_index': 't', 'direction': 'right to left'},
            'control_volume': 'V_ctrl^t concatenates both post-update hidden states at time t',
            'layout': 'Horizontally staggered forward and backward chains with aligned outer inputs; shared central time-indexed outputs receive both post-update states through straight vertical arrows',
        },
        'method_reference': str(METHOD_REFERENCE),
    }, indent=2) + '\n')
    print('Rendered five self-contained SVG diagrams and five static variants in', OUT)


if __name__ == '__main__':
    main()
