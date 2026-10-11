(() => {
  'use strict';

  const players = new Map();
  const template = document.getElementById('player-controls-template');
  const mediaUrls = new Map();

  function loadMedia(video, mode = 'master') {
    const sources = [...video.querySelectorAll('source')];
    const source = sources.find(item => video.canPlayType(item.type)) || sources[0];
    // Python's basic HTTP server does not implement byte ranges. A shared blob
    // makes this short clip fully seekable even on that preview server, while
    // loading the file only once for the gallery and enlarged view.
    const url = mode === 'master' ? source.src : source.src.replace('/comparison.', `/comparison-${mode}.`);
    if (!mediaUrls.has(url)) {
      const result = location.protocol === 'file:' ? Promise.resolve(url) :
        fetch(url).then(response => {
          if (!response.ok) throw new Error(`Media response ${response.status}`);
          return response.blob();
        }).then(blob => URL.createObjectURL(blob)).catch(() => url);
      mediaUrls.set(url, result);
    }
    return mediaUrls.get(url);
  }

  function pauseAll(except) {
    players.forEach(player => {
      if (player !== except) player.pause();
    });
  }

  function createSceneViews(root, video) {
    if (root.dataset.viewLayout !== 'quad') return () => {};
    root.classList.remove('quad-player');
    root.append(document.getElementById('scene-views-template').content.cloneNode(true));
    const grid = root.querySelector('.scene-view-grid');
    const tiles = [...grid.querySelectorAll('canvas')].map((canvas, index) => ({
      canvas, context: canvas.getContext('2d', { alpha: false }),
      x: (index % 2) * 640, y: Math.floor(index / 2) * 360 + 40,
    }));
    let paintedKey;
    function paint(source) {
      tiles.forEach(({ canvas, context, x, y }) => {
        // Only remove the existing 40-pixel caption strips. The full native
        // 640×320 image area, including calibration padding, is unchanged.
        context.drawImage(source, x, y, 640, 320, 0, 0, 640, 320);
      });
      grid.hidden = false;
      root.classList.add('quad-player');
    }
    function render(key, force = false) {
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.seeking) return;
      if (force || key !== paintedKey) {
        paint(video);
        paintedKey = key;
      }
    }
    ['loadeddata', 'seeked', 'pause'].forEach(event => {
      video.addEventListener(event, () => render(undefined, true));
    });
    if (video.poster) {
      const poster = new Image();
      poster.addEventListener('load', () => {
        if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) paint(poster);
      });
      poster.src = video.poster;
    }
    return render;
  }

  function createPlayer(root) {
    const video = root.querySelector('video');
    const renderViews = createSceneViews(root, video);
    const sourceFps = Number(root.dataset.sourceFps);
    const encodedFps = Number(root.dataset.encodedFps);
    const frameCount = Number(root.dataset.frameCount);
    // Some comparison runs retain selected AOPs rather than every capture tick.
    // Step only through real samples, while playback preserves their spacing.
    const sampleTicks = root.dataset.sampleTicks ? root.dataset.sampleTicks.split(',').map(Number) :
      Array.from({ length: frameCount }, (_, index) => index);
    const durationTicks = Number(root.dataset.durationTicks || frameCount);
    const factors = (root.dataset.slowdownFactors || '1,2,4,8,16').split(',').map(Number);
    const previewFactors = (root.dataset.previewFactors || '1,2').split(',').map(Number);
    root.append(template.content.cloneNode(true));
    video.controls = false;

    const playButton = root.querySelector('[data-play]');
    const seek = root.querySelector('[data-seek]');
    const speed = root.querySelector('[data-speed]');
    const speedReadout = root.querySelector('[data-speed-readout]');
    const status = root.querySelector('[data-player-status]');
    const fullscreen = root.querySelector('[data-fullscreen]');
    seek.max = frameCount - 1;
    speed.max = factors.length - 1;
    speed.title = factors.map(factor => factor === 1 ? 'Original' : `${factor}× slower`).join(' · ');
    let currentFrame = 0;
    let scrubbing = false;
    let resumeAfterScrub = false;
    let animationFrame = null;
    let operation = 0;
    let currentMode = 'master';
    let switching = false;
    let wantsToPlay = false;
    const suspensions = new Set();
    let resumeAfterSuspend = false;
    const previews = Object.fromEntries(previewFactors.map(factor => {
      const count = Math.ceil(durationTicks * encodedFps * factor / sourceFps);
      const map = count === 1 ? [sampleAtTick(Math.floor(durationTicks / 2))] :
        Array.from({ length: count }, (_, i) => sampleAtTick(Math.min(durationTicks - 1, Math.round(i * sourceFps / (encodedFps * factor)))));
      return [factor === 1 ? 'original' : `slow${factor}`, map];
    }));
    const player = { video, speed, setSpeed, seekFrame, play, pause, suspend, resume, get frame() { return currentFrame; } };
    players.set(root, player);

    function showStatus(message = '') {
      status.textContent = message;
      status.hidden = !message;
    }

    function sampleAtTick(tick) {
      let index = 0;
      while (index + 1 < sampleTicks.length && sampleTicks[index + 1] <= tick) index++;
      return index;
    }

    function renderFrame(frame) {
      currentFrame = Math.min(frameCount - 1, Math.max(0, frame));
      renderViews(`${currentMode}:${currentFrame}`);
      if (!scrubbing) seek.value = currentFrame;
      seek.setAttribute('aria-valuetext', `${Math.round(currentFrame / Math.max(1, frameCount - 1) * 100)}%`);
      root.querySelector('[data-step="-1"]').disabled = currentFrame === 0;
      root.querySelector('[data-step="1"]').disabled = currentFrame === frameCount - 1;
    }

    function setSpeed(index) {
      index = Math.min(factors.length - 1, Math.max(0, Number(index)));
      const factor = factors[index];
      const resume = wantsToPlay || !video.paused;
      speed.value = index;
      speedReadout.textContent = factor === 1 ? 'Original speed' : `${factor}× slower`;
      speed.setAttribute('aria-valuetext', factor === 1 ? 'Original capture speed' : `${factor} times slower than capture speed`);
      showStatus();
      if (resume) play();
      else applyRate();
    }

    function applyRate() {
      // Fast previews present deterministic captured samples at display rate;
      // the master retains every sample for slow motion and exact frame steps.
      const factor = factors[Number(speed.value)];
      const preview = factor === 1 ? 'original' : `slow${factor}`;
      const rate = currentMode === 'master' && !previews[preview] ? sourceFps / encodedFps / factor : 1;
      video.defaultPlaybackRate = rate;
      video.playbackRate = rate;
    }

    function frameAtTime(time, rounded = false) {
      const index = rounded ? Math.round(time * encodedFps) : Math.floor(time * encodedFps + 0.0001);
      return currentMode === 'master' ? sampleAtTick(index) : previews[currentMode][Math.min(previews[currentMode].length - 1, index)];
    }

    function waitForMedia(event) {
      return new Promise((resolve, reject) => {
        const cleanup = () => {
          video.removeEventListener(event, done);
          video.removeEventListener('error', fail);
        };
        const done = () => { cleanup(); resolve(); };
        const fail = () => { cleanup(); reject(new Error('Media could not load')); };
        video.addEventListener(event, done);
        video.addEventListener('error', fail);
      });
    }

    async function useMode(mode, frame, serial) {
      switching = true;
      try {
        const url = await loadMedia(video, mode);
        if (serial !== operation) return false;
        if (video.src !== url) {
          video.pause();
          currentMode = mode;
          root.dataset.mediaMode = mode;
          const metadata = waitForMedia('loadedmetadata');
          video.src = url;
          video.load();
          await metadata;
        } else if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
          const metadata = waitForMedia('loadedmetadata');
          video.load();
          await metadata;
        }
        if (serial !== operation) return false;
        applyRate();
        const map = previews[mode];
        // A sub-refresh preview can contain a single representative sample.
        // Chromium otherwise repeatedly seeks to time zero without advancing.
        // Present it once; normal slow-motion sequences continue to loop.
        video.loop = root.dataset.loop !== 'false' && (!map || map.length > 1);
        const index = mode === 'master' ? sampleTicks[frame] : map.reduce((best, value, i) =>
          Math.abs(value - frame) < Math.abs(map[best] - frame) ? i : best, 0);
        const sought = waitForMedia('seeked');
        video.currentTime = (index + 0.1) / encodedFps;
        await sought;
        if (serial !== operation) return false;
        renderFrame(mode === 'master' ? frame : map[index]);
        return true;
      } finally {
        if (serial === operation) switching = false;
      }
    }

    function pause() {
      wantsToPlay = false;
      resumeAfterSuspend = false;
      operation++;
      switching = false;
      video.pause();
      renderPlaybackState();
    }

    function suspend(reason) {
      if (!suspensions.size) {
        const wasPlaying = wantsToPlay || !video.paused;
        pause();
        resumeAfterSuspend = wasPlaying;
      }
      suspensions.add(reason);
    }

    function resume(reason) {
      suspensions.delete(reason);
      if (!suspensions.size && resumeAfterSuspend) {
        resumeAfterSuspend = false;
        play();
      }
    }

    function seekFrame(frame) {
      frame = Math.min(frameCount - 1, Math.max(0, Number(frame)));
      renderFrame(frame);
      const serial = ++operation;
      // Always seek the full master, including when the speed control is set
      // to original. Stepping therefore exposes every retained source sample.
      useMode('master', frame, serial).catch(() => showStatus('Video could not load. Reload the page.'));
    }

    async function play() {
      if (document.hidden) suspensions.add('document');
      if (suspensions.size) {
        resumeAfterSuspend = true;
        return;
      }
      showStatus();
      wantsToPlay = true;
      const serial = ++operation;
      const factor = factors[Number(speed.value)];
      const preview = factor === 1 ? 'original' : `slow${factor}`;
      const mode = previews[preview] ? preview : 'master';
      renderPlaybackState();
      try {
        if (!await useMode(mode, currentFrame, serial)) return;
        await video.play();
      } catch (error) {
        if (serial === operation) {
          wantsToPlay = false;
          renderPlaybackState();
          if (error.name !== 'AbortError') showStatus('Press Play to start the video.');
        }
      }
    }

    function renderPlaybackState() {
      const playing = wantsToPlay || !video.paused;
      root.querySelector('[data-play-symbol]').textContent = playing ? 'Ⅱ' : '▶';
      root.querySelector('[data-play-label]').textContent = playing ? 'Pause' : 'Play';
      playButton.setAttribute('aria-label', playing ? 'Pause synchronized views' : 'Play synchronized views');
    }

    playButton.addEventListener('click', () => {
      if (video.paused && !wantsToPlay) play();
      else pause();
    });
    root.querySelectorAll('[data-step]').forEach(button => {
      button.addEventListener('click', () => {
        pause();
        seekFrame(currentFrame + Number(button.dataset.step));
      });
    });
    seek.addEventListener('input', () => {
      if (!scrubbing) {
        resumeAfterScrub = wantsToPlay || !video.paused;
        scrubbing = true;
        pause();
      }
      seekFrame(seek.value);
    });
    function finishScrubbing() {
      if (!scrubbing) return;
      scrubbing = false;
      if (resumeAfterScrub) play();
      resumeAfterScrub = false;
    }
    seek.addEventListener('change', finishScrubbing);
    seek.addEventListener('pointercancel', finishScrubbing);
    seek.addEventListener('blur', finishScrubbing);
    speed.addEventListener('input', () => setSpeed(speed.value));
    fullscreen.hidden = typeof root.requestFullscreen !== 'function';
    fullscreen.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await root.requestFullscreen();
      } catch (error) {
        showStatus('Fullscreen is unavailable in this browser window.');
      }
    });

    // Read the presented video frame rather than independently advancing four
    // clocks. The fallback also reads the same media element's time.
    if ('requestVideoFrameCallback' in video && root.dataset.clock !== 'media-time') {
      const onFrame = (_, metadata) => {
        if (!video.seeking && !switching) renderFrame(frameAtTime(metadata.mediaTime, true));
        video.requestVideoFrameCallback(onFrame);
      };
      video.requestVideoFrameCallback(onFrame);
    } else {
      const onAnimation = () => {
        if (!video.seeking && !switching) renderFrame(frameAtTime(video.currentTime));
        if (!video.paused) animationFrame = requestAnimationFrame(onAnimation);
      };
      video.addEventListener('play', () => {
        cancelAnimationFrame(animationFrame);
        animationFrame = requestAnimationFrame(onAnimation);
      });
      video.addEventListener('pause', () => cancelAnimationFrame(animationFrame));
    }
    video.addEventListener('seeked', () => { if (!switching) renderFrame(frameAtTime(video.currentTime)); });
    video.addEventListener('play', renderPlaybackState);
    video.addEventListener('pause', renderPlaybackState);
    video.addEventListener('ended', () => {
      wantsToPlay = false;
      renderPlaybackState();
    });
    video.addEventListener('error', () => showStatus('Video could not load. Reload the page and check the media path.'));
    setSpeed(Math.max(0, factors.indexOf(Number(root.dataset.defaultSlowdown || 16))));
    renderFrame(0);
    renderPlaybackState();
    loadMedia(video).then(url => { if (operation === 0) video.src = url; });
    if (root.dataset.autoplay !== 'false' && root.getClientRects().length) play();
    return player;
  }

  document.querySelectorAll('.sync-player').forEach(createPlayer);
  window.CoGenRecPlayers = {
    pauseAll,
    play(root) { return players.get(root).play(); },
    pause(root) { players.get(root).pause(); },
    setVisible(root, visible) {
      const player = players.get(root);
      if (visible) player.resume('panel');
      else player.suspend('panel');
    },
    clone(source) {
      const root = source.cloneNode(false);
      root.removeAttribute('id');
      root.dataset.autoplay = 'false';
      root.removeAttribute('data-media-mode');
      const video = source.querySelector('video').cloneNode(true);
      video.removeAttribute('src');
      video.autoplay = false;
      root.append(video);
      createPlayer(root);
      return root;
    },
    copyState(source, target) {
      const from = players.get(source);
      const to = players.get(target);
      to.pause();
      to.setSpeed(from.speed.value);
      to.seekFrame(from.frame);
    },
  };
  document.addEventListener('visibilitychange', () => {
    players.forEach(player => {
      if (document.hidden) player.suspend('document');
      else player.resume('document');
    });
  });
})();
