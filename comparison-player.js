(() => {
  'use strict';

  document.querySelectorAll('.comparison-player').forEach(root => {
    const video = root.querySelector('video');
    const tiles = [...root.querySelectorAll('[data-method-tile]')].map(canvas => ({
      canvas,
      context: canvas.getContext('2d', { alpha: false }),
      index: Number(canvas.dataset.methodTile),
      poster: canvas.parentElement.querySelector('.method-poster'),
    }));
    let animation;
    function paint() {
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
      tiles.forEach(({ canvas, context, index, poster }) => {
        context.drawImage(video, index * 640, 0, 640, 320, 0, 0, 640, 320);
        canvas.hidden = false;
        poster.hidden = true;
      });
    }
    function animate() {
      paint();
      if (!video.paused) animation = requestAnimationFrame(animate);
    }
    video.addEventListener('play', () => {
      cancelAnimationFrame(animation);
      animate();
    });
    video.addEventListener('pause', () => {
      cancelAnimationFrame(animation);
      paint();
    });
    ['loadeddata', 'seeked'].forEach(event => video.addEventListener(event, paint));
  });

  const tabs = [...document.querySelectorAll('[data-task]')];
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(button => button.setAttribute('aria-pressed', String(button === tab)));
      document.querySelectorAll('[data-comparison-panel]').forEach(panel => {
        panel.hidden = panel.dataset.comparisonPanel !== tab.dataset.task;
        panel.querySelectorAll('.sync-player').forEach(root => {
          window.CoGenRecPlayers.setVisible(root, !panel.hidden);
        });
      });
    });
  });

})();
