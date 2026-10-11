# CoGenRec project page

Local preview (reuse the running server if it is already available):

```bash
python3 -m http.server 26800 --bind 127.0.0.1 --directory /data2/myp/published_projects/GenRec/project_page
```

On another computer, open the local port forwarded to this server. Refresh with
Ctrl+F5 after edits. This folder contains all HTML, JavaScript, posters, and media
needed for static hosting; it does not depend on the evaluation output folder at
runtime.

The first scene is 杯子摔碎, CSV row 1, cached COP intervals 66–70. The
gallery card uses those selected assets. The hero contains the
paper title and links only; the former cover video has been removed. Each video frame contains
RGB / TD / SD / CoGenRec in a 2×2 layout, so the four views share one media clock.

- Each cache has 26 inclusive AOP samples at ratio 25. The export retains AOP
  0–24 from each interval, producing 125 samples without repeated endpoints.
- RGB uses `rgb_start` in the first half of each COP interval and `rgb_end` in
  the second half. At ratio 25, AOP 0–12 uses RGB0 and AOP 13–25 uses RGB1;
  shared endpoint deduplication is unchanged. TD, SD, and
  reconstruction use the matching cached AOP index, without additional signal
  processing or generated intermediate RGB frames.
- Speed is based on the **nominal 757 FPS acquisition mode** and approximately
  30 FPS RGB. The evaluation configuration's `fps: 30` is an older video export
  setting, rather than the high-speed acquisition rate. This page does not claim
  clock-calibrated frame timing from device timestamp ticks.
- The complete master stores all samples at 60 encoded FPS. For 4× / 8× / 16×
  slow motion, playback rate is `757 / 60 / slowdown`. Original and 2× slower
  playback use 60 FPS presentation videos with deterministic sampled indices,
  avoiding a requirement to decode hundreds of frames per second. Their
  durations are rounded to the nearest display frame (0.167 s and 0.333 s).
- Seeking and frame stepping always use the complete master, including at the
  original-speed slider setting. The player retains the COP/AOP mapping
  internally. COP/AOP, sample numbers, timestamps, scene indices and
  comparison indices are omitted from the webpage. The default is muted
  autoplay and looping 16× slow motion (128× for the balloon).
- MP4/H.264 is the primary format, with WebM/VP9 as a fallback. Shared in-memory
  blob URLs enable seeking on Python's basic server, which lacks byte-range
  responses. Only the selected format is fetched, once per asset across players.

Asset provenance, hashes, frame indices, and presentation mappings are saved in
`assets/cup-shattering-cop66-70/manifest.json`. Regenerate with:

```bash
/home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/export_cup_scene.py
```

The exporters read existing caches and use CPU ffmpeg; they do not run inference
or modify source data. Real-world results contains six four-view scenes.
Method comparisons contains five populated scenes.
There is no scene selector or training-protocol selector; the global Video
reconstruction / RGB deblurring tabs switch all five rows together.
Scene cards show a frame-rate badge and only Fast motion / HDR / Blur tags,
without descriptive paragraphs. Cup shattering, peach blossoms, and street
bicycles use Fast motion / Blur;
fireworks and the train use all three; the balloon uses Fast motion only.
Display names are Shattering glass, Ground fireworks, Balloon burst, Train
encounter, Peach blossoms, Street bicycles, Spinning disc, Rotating blocks, Cartoon poster, Sunlit facade, and
Passing motorcycle. Train encounter refers to opposing trains meeting, and
retains 600 km/h relative speed beside its name. The paper title is plain text.
Baseline method labels read Official weights; Input RGB and CoGenRec have no
Observation or Ours qualifier.
Each card places its title and right-aligned tags in one compact footer row.
Enlarge scene buttons and their separate dialogs have been removed; the player
keeps its fullscreen button. Gallery and comparison players use one compact
control row on wide cards and two on narrow cards. The speed slider retains
all slowdown choices and shows its selected value without a separate stop-label
row. Body copy uses 17 px text, method names use 16 px, four-view captions use
15 px, and compact tags and controls use 12–14 px. Narrow screens stack cards
and allow tags to wrap within the same title row. Resources contains its main heading and compact link cards,
without a subtitle or descriptive paragraphs in the cards.

## Animated framework diagram

Overview uses a full-width SVG redraw of the manuscript framework.
The section heading sits above the diagram, and the overview description spans
the full content width below it, without a subtitle.
The blue input panel shows COP/AOP on one shared time axis; warm panels show the reconstruction pipeline,
endpoint encoder and bidirectional temporal propagator. All connection arrows
are static; temporal scanning uses a CSS animation. The four detail-fusion feature blocks
use identical solid fills with no opacity animation. The horizontal guidance
arrow aligns with the first feature block's center, and the blocks are labeled
`Ψ(V_ctrl^(0,…,T−1))`. Text and
measurement thumbnails remain stationary. The scan extends from the RGB row
through both AOP regions; exposure windows use a subtle neutral gray background.
Both AOP sections use the same left label column, signal-row spacing, and
thumbnail sizes. The measurement panel has extra horizontal room so headings
remain outside the continuous endpoint selection frames.
The figure omits timeline captions and sample-count labels.
`prefers-reduced-motion` removes
the scanning animation while retaining the complete diagram. HTML `picture` sources
select unconditional `*-static.svg` variants, including when the preference
changes while the page is open.

`framework-interactions.js` progressively renders visible diagrams as inline
SVGs, retaining the ordinary pictures as a fallback. Hover or keyboard focus
links each reconstruction input to its corresponding measurements: RGB0 and
RGB1 each select their own RGB and intra-exposure TD/SD within one continuous
outer frame, with the RGB label as its legend. Individual thumbnails and the
exposure backdrop do not form additional active frames. Between-exposure TD/SD
selects the inter-exposure rows and indexed inputs in the propagator detail.
Each endpoint input also highlights the three shared `0/1` input boxes in the
encoder detail. Hovering or focusing any shared input box highlights both
endpoint inputs and their measurements, since the detail describes both
endpoints. These input links use blue emphasis; encoder module links use orange.
Either endpoint encoder selects both encoders and their detail panel; the
temporal propagator selects its module and detail panel. Emphasis uses pale
fills, outlines and soft shadows without moving sampling positions. Touch taps
toggle emphasis; Enter/Space pins it and Escape clears it. Narrow layouts keep
the same links across separate panels. Instance-specific IDs prevent arrow and
ARIA reference collisions when viewport or motion preferences change.
Right-hand diagram labels use consistent title case and stronger font
weights. The endpoint encoder has a named Cross-Attention Fusion region around
the RGB hierarchy. The three encoded TD scales enter from above and SD scales
from below, aligned with their RGB scales. An output lane below the RGB blocks
collects the native RGB feature and the three fused encoded features into
`F_end,0/1`, separated from the TD/SD input connections. Each input carries the
`0/1` endpoint subscript. The Four Scales caption and stacked feature glyph are omitted.
The propagator detail has separate AOP inputs above the forward chain
and below the backward chain. Forward inputs are `TD_t, SD_t`; backward inputs
are `TD_(t+1), SD_t`, following `CBRDM/TMRGBTSDInterpolation_full.py`.
The upper chain runs left to right and the lower chain right to left. At each
displayed time (0, 1, T−1), features branch after both recurrent blocks and
enter one shared `V_ctrl^t` block between the chains. The upper blocks and inputs
sit slightly to the left of these outputs, and the lower blocks and inputs sit
slightly to the right, so both output branches are straight vertical arrows.

`assets/framework/cogenrec-framework.svg` is the self-contained desktop figure.
Narrow layouts display separate measurement, vertically arranged reconstruction,
encoder and propagator SVGs. Measurement thumbnails come directly from
`output/real_tmrec_varlen_oursdecoder_iter010000_waterball2_cop058_059_gpu6/input_frames/cop000058`.
All TD and SD thumbnails are horizontally mirrored for display; RGB endpoints
and reconstruction thumbnails retain their original orientation. Source PNGs,
NPZ arrays and existing gallery videos are unchanged. The pipeline output
thumbnails use frames 0 and 25 of the same COP58 method cache.

RGB0 and RGB1 exposure windows are centered at `t_0` and `t_25`, with duration
`tau_COP` (three AOP periods). Each contains two valid TD intervals and one
channel-0 SD sample at the center. Inter-exposure SD has 26 sample instants;
TD files 1..25 span the 25 adjacent SD pairs. TD files 0 and 26 are black padding
and are excluded, as are the padding frames in the intra-exposure TD folders.
The graphic shows SD times 0, 1, 2, 23, 24, 25 and TD intervals [0,1], [1,2],
[23,24], [24,25]. All rows share the same time mapping and explicit middle
omission; SD dots mark instants and TD capped spans mark intervals. The exposure
windows overlap the between-endpoint range near both centers, reflecting the
actual temporal relationship rather than three disjoint capture stages.

All thumbnails are embedded PNGs; diagram text, boxes and connections are vector
elements. No external fonts, image requests or animation libraries are needed.
Source paths, hashes, mirroring and temporal mappings are saved in the asset manifest.
Regeneration also updates the SVG and interaction-script URLs in `index.html`
with content hashes, including all static picture sources, so a normal reload
fetches changed diagrams instead of reusing previously cached images.

Regenerate from the COP58 inputs and reconstruction cache:

```bash
/home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/render_framework_diagram.py
```

## Additional selected scenes

- **Ground fireworks:** COP intervals 455–457, 757 FPS. Reconstruction pixels
  come directly from `fireworks_on_ground_01_calibrated.mp4`, rather than the
  uncalibrated prediction caches. Its 76-frame order retains the preceding
  interval's AOP 25 and drops the following AOP 0. The paired RGB/TD/SD caches
  follow that same mapping. The prediction in the supplied MP4 has an embedded
  label over its first 36 image rows; all four views receive the same 36-row top
  crop and centered padding, preserving the remaining image scale and alignment.
  No new color correction is applied.
- **Balloon burst:** COP 54, AOP **80–100 inclusive**, exactly 21
  samples. Both named endpoint PNGs are checked against the reconstruction
  cache. The page uses the requested 3000 FPS label and clock (the source scene
  name contains `3030`). The ≈7 ms selection defaults to 128× slow motion and
  also offers original / 2× / 4× / 8× / 16× / 32× / 64×. Each displayed AOP keeps
  its original index, including the final AOP 100. RGB is intentionally split
  within this selected window: **AOP 80–90 uses RGB0, AOP 91–100 uses RGB1**.
  This display mapping is relative to the cropped selection, even though the
  entire selection lies in the latter half of the original COP interval.
- **Train encounter (600 km/h relative speed):** 1515 FPS, from **COP 79 / AOP 10** through **COP 81 /
  AOP 25 inclusive**. Reconstruction is extracted directly from the supplied
  `real_tmrec_varlen_stage1_iter030000_railway_gpu7_native/railway_calibrated.mp4`;
  no calibration is rerun and no uncalibrated prediction cache is substituted.
  The source covers COP 77–87 at ratio 50, with 551 frames after boundary
  deduplication. Source frames **110–225** map to 116 retained samples:
  COP 79 / AOP 10–50, COP 80 / AOP 1–50, COP 81 / AOP 1–25. Within each
  original ratio-50 interval, AOP 0–25 uses RGB0 and AOP 26–50 uses RGB1;
  TD/SD use the corresponding cached AOP. As for fireworks, all four views
  receive the same 36-row crop to remove the supplied video's embedded label.
  Defaults to 16× slow motion, with original / 2× / 4× / 8× / 16× controls;
  original / 2× / 4× use display-rate previews and exact frame stepping always
  accesses the complete 116-sample master.
- **Peach blossoms / Street bicycles:** COP **26–28** / **98–100**, 757 FPS,
  using worker 003 / CSV row 55 and worker 000 / CSV row 66 respectively.
  Both use the cached `001_Ours_with_exposure_augmentation` reconstruction and
  matching RGB/SD references from the specified three-variant run. TD is
  decoded from the original sensor recordings listed in `100demo_info.csv`.
  Each
  selection retains **21 real AOP samples** at AOP 0, 4, 8, 12, 16, 20, 24 per
  COP and holds them across **75 display ticks** with their original spacing.
  RGB switches after the interval midpoint: the first four retained AOPs use
  RGB0 and the last three use RGB1. All four native 640×320 views share one
  encoded video frame without cropping. Both default to looping 16× slow
  motion and offer original / 2× / 4× / 8× / 16×; stepping visits only actual
  samples. Source-frame mappings and hashes are included in their manifests.
  TD now shows the original single-AOP measurement at every retained sample,
  rather than the model input's accumulated TD with an artificial zero at
  AOP 0. This removes the black segment-start flashes. The decoder follows
  the dataset's one-sample offset and exposure-center mapping (11 exposure
  periods for peach, 5 for bicycles). Every selected raw SD image is checked
  for exact equality with cached SD to validate temporal and spatial alignment.
  The original rod frame indices, timestamps, recording hashes, visualization
  settings and alignment check are recorded in `raw_td_source` and sample maps.
  RGB, SD, reconstruction, selected AOPs and capture timing retain their prior
  values. Re-exporting requires the raw recording paths to be accessible.

  Regenerate either scene by key (`peach` / `bicycles`), or both:

  ```bash
  /home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/export_cached_scenes.py all
  ```

## Official-checkpoint comparisons

- **Spinning disc / Rotating blocks:** COP **2–3** / **40–41**, 757 FPS capture
  mode, with Fast motion and Blur tags. The specified three-variant run
  retains only AOP **0, 4, 8, 12, 16, 20, 24**, giving **14 actual samples** in
  each selection. Worker 002 / CSV row 89 supplies the turntable, and worker
  001 / CSV row 56 supplies the blocks. Both use
  `001_Ours_with_exposure_augmentation` as CoGenRec. They have been moved from
  the Real-world results gallery into the comparison section.
- **Cartoon poster:** COP **185** only, worker 003 / CSV row 3, **7 actual samples**,
  25 display ticks, ≈0.033 s capture. Source scene `HDR卡通人.mp4`.
- **Sunlit facade:** COP **186–187**, worker 001 / CSV row 1, **14 actual
  samples**, 50 display ticks, ≈0.066 s capture. Source scene `HDR建行.mp4`.
- **Passing motorcycle:** COP **752–754**, worker 003 / CSV row 60, **21 actual
  samples**, 75 display ticks, ≈0.099 s capture. Source scene `摩托农夫山泉.mp4`.
  The two HDR scenes occupy the former reserved positions; motorcycle adds a
  fifth comparison row. All five selections use the same nominal 757 FPS mode,
  ratio 25, retained AOP set, and checkpoint policy below.

  Video columns are Input RGB, Tianmouc-UNet (`008_*official_weights`), IGFNet
  (`005_*official_weights`), CBRDM (`002_*official_weights`), and CoGenRec
  (`001_Ours_with_exposure_augmentation`). Only official baseline checkpoint
  entries are loaded; no retrained baseline or no-exposure Ours is substituted.
  Worker manifests, actual checkpoint paths, cache paths, and SHA-256 hashes
  are recorded in each exported comparison manifest.

  Each decoded video frame contains five **640×320 unscaled** method tiles in
  one 3200×320 strip. Five responsive canvases render those tiles from the same
  video element, so methods share one media clock without independent-video
  drift. HTML labels remain readable as the grid wraps on smaller displays.
  Posters use the first retained sample. No image rows are cropped away.

  RGB switches from `rgb_start` to `rgb_end` after the COP interval midpoint.
  With retained AOPs 0, 4, 8, 12, 16, 20, 24, the first four samples show RGB0
  and the last three show RGB1. Each retained sample, including its chosen RGB,
  is held until the next cached AOP. Every reconstruction method uses the
  matching cached AOP throughout. An exact midpoint belongs to RGB0.

  Playback preserves the actual AOP timing: each retained sample is held until
  the next, including the one-tick AOP 24 → next COP AOP 0 transition. The
  complete presentation stores 25 display ticks per selected COP at 60 encoded
  FPS, with **7 unique samples per COP**; repeated display frames are not inferred
  reconstructions. A two-COP selection lasts 50/757 ≈ 0.066 s at original speed,
  and ≈1.057 s at the default 16× slow motion. The seek control steps through
  only the genuine samples, retains their real COP/AOP mapping internally,
  and seeks to `sample_tick / 60`. The manifests record the
  retained sample count. Original / 2× previews sample the
  held timeline at display rate; 4× / 8× / 16× use the complete presentation.

  RGB deblurring adds official STGDNet (`011_*official_weights`). Its
  cache has exactly one **F0** image per COP, so it is shown only at AOP 0.
  Each scene shows only the first selected COP (2, 40, 185, 186, or 752), with
  six full-resolution PNGs. There is no COP caption, COP picker or detail-crop
  section. The other four reconstruction
  methods use `frames[0]`, and Input RGB uses `rgb_start` at the same endpoint.
  Only the first selected COP's full-resolution images are exported. Unused
  additional endpoints, detail crops, and combined comparison posters are omitted.
  Switching to RGB deblurring pauses only the comparison videos before hiding
  their players; switching back resumes those that were playing.

Each gallery player draws four 640×320 canvas tiles from the same decoded
1280×720 video frame. It omits only the existing 40-pixel caption strips at
the top of each source tile, and displays larger HTML RGB / TD / SD / CoGenRec
captions instead. The full image areas, source files and timing are retained,
including any calibration padding. The player performs no TD substitutions;
the two scenes above use raw TD prepared by their exporter. Posters use the
same tile coordinates. Without JavaScript, the native four-view video remains
available. All page videos autoplay concurrently. Hiding video
comparisons with the RGB deblurring tab pauses only those comparisons; returning
resumes the ones that were playing. A hidden browser tab suspends playback and
restores it on return, preserving manual pauses. Fullscreen shows the same
four-view canvas layout or comparison methods with the compact controls.

Regenerate these scenes, or pass `fireworks` / `balloon` / `railway` to export one:

```bash
/home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/export_selected_scenes.py all
```

Regenerate all official comparisons, or pass one or more scene keys
(`turntable`, `blocks`, `hdr-cartoon`, `hdr-bank`, `motorcycle`):

```bash
/home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/export_method_comparisons.py all
/home/yapeng/anaconda3/envs/pro6000/bin/python /data2/myp/published_projects/GenRec/project_page/tools/render_method_comparisons.py
```

Comparison assets live in `assets/comparisons/<scene>/`. Their manifests
distinguish retained `samples` (7 per COP) from held `encoded_frames` (25 per COP), list both method sets, and
record the displayed first-COP endpoint images. `data-sample-ticks` and
`data-duration-ticks` provide the same timing to the player; `data-clock`
selects media-time updates for the canvas source video. Existing dense scenes
omit those attributes and retain their original behavior. Shared cache settings
for comparisons and the two additional gallery scenes live in
`tools/cache_sources.py`; there is no separate four-view rotation exporter.

The asset tree contains the current page's media, dynamically selected speed
variants, and provenance manifests. Both MP4 and WebM are needed for browser
compatibility. The framework renderer publishes the complete desktop figure
and the four narrow-layout panels, each with a reduced-motion variant. Its
desktop reconstruction panel is embedded directly into the complete figure,
so an unused standalone copy is not exported.

Each asset folder includes a manifest with its exact source files, hashes,
calibrated-video frame mapping where applicable, and all retained AOP indices.
Fast presentation videos select captured samples at display rate. For an event
shorter than one display interval, the original and 2× preview use one middle
sample, and their visible duration is limited by screen refresh. Slow motion
and frame stepping expose the entire selected event. Single-sample previews
play once and hold the image, avoiding repeated zero-time seeks in Chromium;
the longer slow-motion sequences loop normally.
