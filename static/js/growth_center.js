(function () {
  const shell = document.getElementById('growth-dashboard');
  if (!shell) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  let busy = false;

  function element(name, attributes) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function readData(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;',
    })[character]);
  }

  function renderChart(container, data, config) {
    const svg = container.querySelector('svg');
    if (!svg || !data || !Array.isArray(data.labels)) return;

    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const width = 720;
    const height = 260;
    const padding = { top: 14, right: 16, bottom: 34, left: 46 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const labels = data.labels;

    if (!labels.length) {
      const text = element('text', {
        x: width / 2,
        y: height / 2,
        'text-anchor': 'middle',
        class: 'gc-axis-label',
      });
      text.textContent = 'No data in this range';
      svg.appendChild(text);
      return;
    }

    const values = config.series.flatMap((series) => data[series.key] || []);
    const maxValue = Math.max(1, ...values);
    const tickCount = 4;

    for (let tick = 0; tick <= tickCount; tick += 1) {
      const ratio = tick / tickCount;
      const y = padding.top + plotHeight - plotHeight * ratio;
      svg.appendChild(element('line', {
        x1: padding.left,
        x2: width - padding.right,
        y1: y,
        y2: y,
        class: 'gc-grid-line',
      }));
      const label = element('text', {
        x: padding.left - 9,
        y: y + 4,
        'text-anchor': 'end',
        class: 'gc-axis-label',
      });
      label.textContent = Math.round(maxValue * ratio).toLocaleString();
      svg.appendChild(label);
    }

    const labelStep = Math.max(1, Math.ceil(labels.length / 7));
    labels.forEach((label, index) => {
      if (index % labelStep !== 0 && index !== labels.length - 1) return;
      const x = padding.left + (labels.length === 1 ? plotWidth / 2 : (plotWidth * index) / (labels.length - 1));
      const text = element('text', {
        x: x,
        y: height - 10,
        'text-anchor': 'middle',
        class: 'gc-axis-label',
      });
      text.textContent = label;
      svg.appendChild(text);
    });

    config.series.forEach((series) => {
      const points = (data[series.key] || []).map((value, index) => {
        const x = padding.left + (labels.length === 1 ? plotWidth / 2 : (plotWidth * index) / (labels.length - 1));
        const y = padding.top + plotHeight - (Number(value) / maxValue) * plotHeight;
        return { x: x, y: y, value: Number(value) };
      });
      if (!points.length) return;

      const path = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
      svg.appendChild(element('path', { d: path, class: `gc-line gc-line-${series.className}` }));

      points.forEach((point, index) => {
        const circle = element('circle', {
          cx: point.x,
          cy: point.y,
          r: 4,
          class: `gc-point gc-point-${series.className}`,
          'data-label': labels[index] || '',
          'data-series': series.label,
          'data-value': point.value.toLocaleString(),
        });
        svg.appendChild(circle);
      });
    });
  }

  function renderCharts() {
    renderChart(shell.querySelector('[data-chart="traffic"]'), readData('gc-traffic-data'), {
      series: [
        { key: 'visitors', label: 'Visitors', className: 'visitors' },
        { key: 'page_views', label: 'Page Views', className: 'views' },
      ],
    });
    renderChart(shell.querySelector('[data-chart="growth"]'), readData('gc-growth-data'), {
      series: [
        { key: 'new', label: 'New Visitors', className: 'new' },
        { key: 'returning', label: 'Returning Visitors', className: 'returning' },
      ],
    });
  }

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  async function refresh(options) {
    if (busy) return;
    busy = true;

    const refreshButton = shell.querySelector('.gc-refresh');
    if (refreshButton) refreshButton.classList.add('is-loading');

    const params = new URLSearchParams(window.location.search);
    Object.entries(options || {}).forEach(([key, value]) => {
      if (key !== '_refresh') setParam(params, key, value);
    });

    if (params.get('range') === 'custom') {
      setParam(params, 'start', (shell.querySelector('.gc-start-date') || {}).value);
      setParam(params, 'end', (shell.querySelector('.gc-end-date') || {}).value);
    } else {
      params.delete('start');
      params.delete('end');
    }

    if (options && options._refresh) params.set('_', String(Date.now()));
    else params.delete('_');

    try {
      const response = await fetch(`${shell.dataset.dashboardUrl}?${params.toString()}`, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Analytics request failed');

      const payload = await response.json();
      shell.innerHTML = payload.html;

      const cleanParams = new URLSearchParams(params);
      cleanParams.delete('_');
      const query = cleanParams.toString();
      history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
      renderCharts();
    } catch (error) {
      window.location.reload();
    } finally {
      busy = false;
    }
  }

  function showTooltip(event) {
    const point = event.target.closest('.gc-point');
    if (!point) return;
    const chart = point.closest('.gc-chart');
    const tooltip = chart && chart.querySelector('.gc-tooltip');
    if (!chart || !tooltip) return;

    tooltip.innerHTML = `<strong>${escapeHtml(point.dataset.label)}</strong>${escapeHtml(point.dataset.series)}: ${escapeHtml(point.dataset.value)}`;
    tooltip.hidden = false;

    const chartRect = chart.getBoundingClientRect();
    const pointRect = point.getBoundingClientRect();
    tooltip.style.left = `${Math.min(chartRect.width - 150, Math.max(0, pointRect.left - chartRect.left + 8))}px`;
    tooltip.style.top = `${Math.max(0, pointRect.top - chartRect.top - 52)}px`;
  }

  function hideTooltip(event) {
    if (!event.target.closest || !event.target.closest('.gc-point')) return;
    const chart = event.target.closest('.gc-chart');
    const tooltip = chart && chart.querySelector('.gc-tooltip');
    if (tooltip) tooltip.hidden = true;
  }

  document.addEventListener('change', (event) => {
    const target = event.target;
    if (target.matches('.gc-range-select')) {
      const isCustom = target.value === 'custom';
      const custom = shell.querySelector('.gc-custom-range');
      if (custom) custom.hidden = !isCustom;
      refresh({ range: target.value, custom: null });
    } else if (target.matches('.gc-grain-select')) {
      refresh({ grain: target.value });
    } else if (target.matches('.gc-source-select')) {
      refresh({ source: target.value });
    } else if (target.matches('.gc-sort-select')) {
      refresh({ sort: target.value });
    }
  });

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (target.closest('.gc-refresh')) {
      refresh({ _refresh: true });
    } else if (target.closest('.gc-date-apply')) {
      refresh({});
    } else if (target.closest('.gc-reset')) {
      refresh({ range: '7d', grain: '', source: '', sort: 'views', start: '', end: '' });
    } else {
      const sourceRow = target.closest('.gc-source-row');
      if (sourceRow) {
        const select = shell.querySelector('.gc-source-select');
        const nextSource = select && select.value === sourceRow.dataset.source ? '' : sourceRow.dataset.source;
        refresh({ source: nextSource });
      }
    }
  });

  shell.addEventListener('mousemove', showTooltip);
  shell.addEventListener('mouseout', hideTooltip);

  renderCharts();
})();
