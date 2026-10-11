(() => {
  'use strict';

  const figure = document.querySelector('.method-diagram');
  if (!figure) return;

  const pictures = [...figure.querySelectorAll('picture')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const requests = new Map();
  const revisions = new WeakMap();
  // The detailed encoder shares its 0/1 inputs between the two endpoint
  // instances. An individual endpoint links to those shared inputs; the
  // shared inputs link back to both endpoint measurement groups.
  const endpointLinks = {
    'endpoint-0': ['endpoint-0', 'endpoint-inputs'],
    'endpoint-1': ['endpoint-1', 'endpoint-inputs'],
    'endpoint-inputs': ['endpoint-inputs', 'endpoint-0', 'endpoint-1'],
  };
  let hovered = null;
  let focused = null;
  let pinned = null;
  let started = false;
  let resizeFrame = 0;

  function hotspot(node) {
    if (!(node instanceof Element)) return null;
    const group = node.closest('[data-hotspot]');
    return group && figure.contains(group) ? group : null;
  }

  function renderHighlight() {
    const active = hovered || focused || pinned;
    const activeGroups = new Set(endpointLinks[active] || [active]);
    if (active) figure.dataset.activeGroup = active;
    else delete figure.dataset.activeGroup;
    for (const group of figure.querySelectorAll('[data-highlight]')) {
      group.classList.toggle('is-highlighted', activeGroups.has(group.dataset.highlight));
    }
    for (const group of figure.querySelectorAll('[data-hotspot]')) {
      group.setAttribute('aria-pressed', String(group.dataset.hotspot === pinned));
    }
  }

  function imageURL(picture) {
    for (const source of picture.querySelectorAll('source')) {
      if (!source.media || window.matchMedia(source.media).matches) {
        return new URL(source.getAttribute('srcset'), document.baseURI).href;
      }
    }
    return new URL(picture.querySelector('img').getAttribute('src'), document.baseURI).href;
  }

  function inlineDiagram(markup, instance) {
    const parsed = new DOMParser().parseFromString(markup, 'image/svg+xml');
    if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') {
      throw new Error('Invalid framework SVG');
    }
    const svg = document.importNode(parsed.documentElement, true);
    // Desktop and narrow panels can coexist after a viewport change. Namespace
    // all IDs, ARIA references and arrow markers to their actual page instance.
    const ids = new Map([...svg.querySelectorAll('[id]')]
      .map(node => [node.id, `framework-${instance}-${node.id}`]));
    for (const node of [svg, ...svg.querySelectorAll('*')]) {
      if (node.id) node.id = ids.get(node.id);
      for (const attribute of [...node.attributes]) {
        if (attribute.name === 'id') continue;
        let value = attribute.value.replace(/url\(#([^)]+)\)/g,
          (match, id) => ids.has(id) ? `url(#${ids.get(id)})` : match);
        if (attribute.name.startsWith('aria-')) {
          value = value.split(' ').map(id => ids.get(id) || id).join(' ');
        } else if ((attribute.localName === 'href') && value.startsWith('#') && ids.has(value.slice(1))) {
          value = `#${ids.get(value.slice(1))}`;
        }
        if (value !== attribute.value) node.setAttribute(attribute.name, value);
      }
      // An atomic image role would hide the keyboard-accessible hotspots.
      if (node.localName === 'svg') node.setAttribute('role', 'group');
    }
    const [,, width, height] = svg.getAttribute('viewBox').split(/\s+/);
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.dataset.diagramInline = '';
    return svg;
  }

  async function enhance(picture, instance) {
    const url = imageURL(picture);
    if (picture.dataset.inlineUrl === url) return;
    const revision = (revisions.get(picture) || 0) + 1;
    revisions.set(picture, revision);
    try {
      if (!requests.has(url)) {
        requests.set(url, fetch(url).then(response => {
          if (!response.ok) throw new Error(`Framework image returned ${response.status}`);
          return response.text();
        }).catch(error => { requests.delete(url); throw error; }));
      }
      const markup = await requests.get(url);
      if (revisions.get(picture) !== revision || imageURL(picture) !== url) return;
      const svg = inlineDiagram(markup, instance);
      const previous = picture.querySelector('[data-diagram-inline]');
      if (previous) previous.replaceWith(svg);
      else picture.append(svg);
      picture.dataset.inlineUrl = url;
      picture.classList.add('framework-inline');
      hovered = null;
      focused = null;
      renderHighlight();
    } catch (error) {
      // The ordinary picture remains a usable fallback without fetch or JS.
      console.warn('Framework interaction unavailable:', error.message);
    }
  }

  function refresh() {
    if (!started) return;
    pictures.forEach((picture, instance) => {
      if (picture.getClientRects().length) void enhance(picture, instance);
    });
  }

  figure.addEventListener('pointerover', event => {
    if (event.pointerType === 'touch') return;
    hovered = hotspot(event.target)?.dataset.hotspot || null;
    renderHighlight();
  });
  figure.addEventListener('pointerout', event => {
    if (event.pointerType === 'touch') return;
    hovered = hotspot(event.relatedTarget)?.dataset.hotspot || null;
    renderHighlight();
  });
  figure.addEventListener('focusin', event => {
    const group = hotspot(event.target);
    focused = group?.matches(':focus-visible') ? group.dataset.hotspot : null;
    renderHighlight();
  });
  figure.addEventListener('focusout', event => {
    const group = hotspot(event.relatedTarget);
    focused = group?.matches(':focus-visible') ? group.dataset.hotspot : null;
    renderHighlight();
  });
  figure.addEventListener('pointerup', event => {
    if (event.pointerType !== 'touch') return;
    const group = hotspot(event.target);
    if (group) {
      pinned = pinned === group.dataset.hotspot ? null : group.dataset.hotspot;
      focused = null;
      renderHighlight();
    }
  });
  figure.addEventListener('keydown', event => {
    const group = hotspot(event.target);
    if (group && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      pinned = pinned === group.dataset.hotspot ? null : group.dataset.hotspot;
      renderHighlight();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      hovered = focused = pinned = null;
      renderHighlight();
    }
  });
  document.addEventListener('pointerdown', event => {
    if (!hotspot(event.target)) {
      pinned = focused = null;
      renderHighlight();
    }
  });
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      hovered = focused = null;
      renderHighlight();
      refresh();
    });
  });
  reducedMotion.addEventListener('change', refresh);

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      started = true;
      refresh();
      observer.disconnect();
    }, { rootMargin: '240px' });
    observer.observe(figure);
  } else {
    started = true;
    refresh();
  }
})();
