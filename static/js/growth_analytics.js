(function () {
  const shell = document.getElementById('growth-dashboard');
  const status = document.getElementById('ga-status');
  if (!shell) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const COLORS = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#e11d48', '#0891b2', '#64748b', '#be123c'];
  let busy = false;
  let searchTimer = null;

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

  function setStatus(message, isError) {
    if (!status) return;
    if (!message) {
      status.hidden = true;
      status.textContent = '';
      status.classList.remove('ga-error');
      return;
    }
    status.hidden = false;
    status.textContent = message;
    status.classList.toggle('ga-error', Boolean(isError));
  }

  function renderLine(container, data, config) {
    const svg = container && container.querySelector('svg');
    if (!svg || !data || !Array.isArray(data.labels)) return;

    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    const width = viewBox && viewBox.width ? viewBox.width : 720;
    const height = viewBox && viewBox.height ? viewBox.height : 260;
    const padding = { top: 14, right: 16, bottom: 34, left: 46 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const labels = data.labels;
    const values = config.series.flatMap((series) => data[series.key] || []);
    const maxValue = Math.max(1, ...values);

    for (let tick = 0; tick <= 4; tick += 1) {
      const ratio = tick / 4;
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

  function renderDonut(container, data) {
    if (!container) return;
    const rows = Array.isArray(data) ? data.filter((row) => row.count > 0) : [];
    const total = rows.reduce((sum, row) => sum + row.count, 0);

    if (!rows.length || !total) {
      container.style.background = 'var(--gc-surface-alt)';
      container.textContent = '0';
      return;
    }

    let start = 0;
    const stops = rows.map((row, index) => {
      const end = start + (row.count / total) * 100;
      const segment = `${COLORS[index % COLORS.length]} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
      start = end;
      return segment;
    });
    container.style.background = `conic-gradient(${stops.join(', ')})`;
    container.innerHTML = `<span>${total.toLocaleString()}</span>`;
  }

  function renderCharts() {
    const metricSelect = shell.querySelector('.ga-metric-select');
    const metric = metricSelect ? metricSelect.value : 'visitors';
    const metricLabel = metricSelect && metricSelect.selectedOptions[0] ? metricSelect.selectedOptions[0].textContent : 'Visitors';
    renderLine(shell.querySelector('[data-chart="traffic"]'), readData('ga-traffic-data'), {
      series: [{ key: metric, label: metricLabel, className: metric === 'page_views' ? 'views' : metric }],
    });
    renderLine(shell.querySelector('[data-chart="growth"]'), readData('ga-growth-data'), {
      series: [
        { key: 'new', label: 'New', className: 'new' },
        { key: 'returning', label: 'Returning', className: 'returning' },
      ],
    });
    renderLine(shell.querySelector('[data-chart="page"]'), readData('ga-page-data'), {
      series: [{ key: metric === 'page_views' ? 'page_views' : metric, label: metricLabel, className: metric === 'page_views' ? 'views' : metric }],
    });
    renderDonut(shell.querySelector('[data-donut="source"]'), readData('ga-source-data'));
    renderDonut(shell.querySelector('[data-donut="device"]'), readData('ga-device-data'));
  }

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  async function refresh(options) {
    if (busy) return;
    busy = true;
    shell.classList.add('ga-loading');
    setStatus('Loading analytics…', false);

    const params = new URLSearchParams(window.location.search);
    Object.entries(options || {}).forEach(([key, value]) => {
      if (key !== '_refresh') setParam(params, key, value);
    });

    if (params.get('range') === 'custom') {
      const start = shell.querySelector('.ga-start-date');
      const end = shell.querySelector('.ga-end-date');
      setParam(params, 'start', start ? start.value : '');
      setParam(params, 'end', end ? end.value : '');
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
      setStatus('', false);
    } catch (error) {
      setStatus('Unable to refresh analytics. Please try again.', true);
    } finally {
      busy = false;
      shell.classList.remove('ga-loading');
    }
  }

  function showTooltip(event) {
    const point = event.target.closest ? event.target.closest('.gc-point') : null;
    if (!point) return;
    const chart = point.closest('.ga-chart, .ga-dual-chart');
    const tooltip = chart && chart.querySelector('.gc-tooltip');
    if (!chart || !tooltip) return;

    tooltip.innerHTML = `<strong>${escapeHtml(point.dataset.label)}</strong>${escapeHtml(point.dataset.series)}: ${escapeHtml(point.dataset.value)}`;
    tooltip.hidden = false;

    const chartRect = chart.getBoundingClientRect();
    const pointRect = point.getBoundingClientRect();
    tooltip.style.left = `${Math.min(Math.max(chartRect.width - 170, 0), Math.max(0, pointRect.left - chartRect.left + 8))}px`;
    tooltip.style.top = `${Math.max(0, pointRect.top - chartRect.top - 52)}px`;
  }

  function hideTooltip(event) {
    if (!event.target.closest || !event.target.closest('.gc-point')) return;
    const chart = event.target.closest('.ga-chart, .ga-dual-chart');
    const tooltip = chart && chart.querySelector('.gc-tooltip');
    if (tooltip) tooltip.hidden = true;
  }

  document.addEventListener('change', (event) => {
    const target = event.target;
    if (target.matches('.ga-range-select')) {
      const custom = shell.querySelector('.ga-custom-range');
      if (custom) custom.hidden = target.value !== 'custom';
      refresh({ range: target.value, start: '', end: '' });
    } else if (target.matches('.ga-compare')) {
      refresh({ compare: target.checked ? '1' : '0' });
    } else if (target.matches('.ga-device-select')) {
      refresh({ device: target.value, page: '', landing_page: '' });
    } else if (target.matches('.ga-source-select')) {
      refresh({ source: target.value, page: '', landing_page: '' });
    } else if (target.matches('.ga-landing-select')) {
      refresh({ landing: target.value, page: '', landing_page: '' });
    } else if (target.matches('.ga-metric-select')) {
      refresh({ metric: target.value });
    } else if (target.matches('.ga-grain-select')) {
      refresh({ grain: target.value });
    } else if (target.matches('.ga-sort-select')) {
      refresh({ sort: target.value, dir: '', page: '', landing_page: '' });
    }
  });

  document.addEventListener('input', (event) => {
    if (!event.target.matches('.ga-search-input')) return;
    window.clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = window.setTimeout(() => refresh({ q: value, page: '', landing_page: '' }), 350);
  });

  document.addEventListener('click', (event) => {
    const target = event.target;

    if (target.closest('.ga-refresh')) {
      refresh({ _refresh: true });
    } else if (target.closest('.ga-date-apply')) {
      refresh({});
    } else if (target.closest('.ga-reset')) {
      refresh({
        range: '7d',
        start: '',
        end: '',
        compare: '',
        device: '',
        source: '',
        landing: '',
        q: '',
        metric: 'visitors',
        grain: '',
        sort: 'views',
        dir: '',
        page: '',
        landing_page: '',
        page_path: '',
      });
    } else if (target.closest('.ga-section-link')) {
      const link = target.closest('.ga-section-link');
      event.preventDefault();
      refresh({
        section: link.dataset.section,
        page_path: link.dataset.section === 'pages' ? undefined : '',
        page: '',
        landing_page: '',
      });
    } else if (target.closest('.ga-source-row')) {
      const row = target.closest('.ga-source-row');
      const select = shell.querySelector('.ga-source-select');
      const next = select && select.value === row.dataset.source ? '' : row.dataset.source;
      refresh({ source: next, page: '', landing_page: '' });
    } else if (target.closest('.ga-breakdown-row[data-source]')) {
      const row = target.closest('.ga-breakdown-row[data-source]');
      const select = shell.querySelector('.ga-source-select');
      const next = select && select.value === row.dataset.source ? '' : row.dataset.source;
      refresh({ source: next, page: '', landing_page: '' });
    } else if (target.closest('.ga-breakdown-row[data-device]')) {
      const row = target.closest('.ga-breakdown-row[data-device]');
      const select = shell.querySelector('.ga-device-select');
      const next = select && select.value === row.dataset.device ? '' : row.dataset.device;
      refresh({ device: next, page: '', landing_page: '' });
    } else if (target.closest('.ga-sortable-table th button')) {
      const button = target.closest('.ga-sortable-table th button');
      const sort = button.dataset.sort;
      const params = new URLSearchParams(window.location.search);
      const dir = params.get('sort') === sort && params.get('dir') !== 'asc' ? 'asc' : 'desc';
      refresh({ sort: sort, dir: dir, page: '', landing_page: '' });
    } else if (target.closest('.ga-pagination button')) {
      const button = target.closest('.ga-pagination button');
      const key = button.dataset.pagination === 'landing' ? 'landing_page' : 'page';
      refresh({ [key]: button.dataset.page });
    } else if (target.closest('.ga-page-link')) {
      refresh({ section: 'pages', page_path: target.closest('.ga-page-link').dataset.pagePath, page: '' });
    } else if (target.closest('.ga-clear-page')) {
      refresh({ page_path: '' });
    }
  });

  shell.addEventListener('mousemove', showTooltip);
  shell.addEventListener('mouseout', hideTooltip);

  renderCharts();
})();
