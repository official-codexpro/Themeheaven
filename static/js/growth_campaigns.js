(function () {
  const shell = document.getElementById('growth-campaigns');
  const status = document.getElementById('gccamp-status');
  if (!shell) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const COLORS = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#e11d48', '#0891b2', '#64748b', '#be123c'];
  const SERIES = [
    { key: 'visitors', label: 'Visitors', className: 'new' },
    { key: 'sessions', label: 'Visits', className: 'returning' },
    { key: 'page_views', label: 'Page Views', className: 'views' },
  ];
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

  async function copyText(value) {
    if (!value) {
      setStatus('There is no URL to copy yet.', true);
      return;
    }
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
      } else {
        const helper = document.createElement('textarea');
        helper.value = value;
        helper.setAttribute('readonly', '');
        helper.style.position = 'fixed';
        helper.style.opacity = '0';
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        document.body.removeChild(helper);
      }
      setStatus('URL copied to clipboard.', false);
    } catch (error) {
      setStatus('Unable to copy URL. Copy it manually from the field.', true);
    }
  }

  function renderLine(container, data) {
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
    const values = SERIES.flatMap((series) => data[series.key] || []);
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

    SERIES.forEach((series) => {
      const points = (data[series.key] || []).map((value, index) => {
        const x = padding.left + (labels.length === 1 ? plotWidth / 2 : (plotWidth * index) / (labels.length - 1));
        const y = padding.top + plotHeight - (Number(value) / maxValue) * plotHeight;
        return { x: x, y: y, value: Number(value) };
      });
      if (!points.length) return;

      svg.appendChild(element('path', {
        d: points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '),
        class: `gc-line gc-line-${series.className}`,
      }));
      points.forEach((point, index) => {
        svg.appendChild(element('circle', {
          cx: point.x,
          cy: point.y,
          r: 4,
          class: `gc-point gc-point-${series.className}`,
          'data-label': labels[index] || '',
          'data-series': series.label,
          'data-value': point.value.toLocaleString(),
        }));
      });
    });
  }

  function renderDonut(container, data) {
    if (!container) return;
    const rows = Array.isArray(data) ? data.filter((row) => row.count > 0) : [];
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    if (!rows.length || !total) {
      container.style.background = 'var(--gc-surface-alt, #f8fafc)';
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
    renderLine(shell.querySelector('[data-chart="campaign-traffic"]'), readData('gccamp-chart-data'));
    renderDonut(shell.querySelector('[data-donut="device"]'), readData('gccamp-device-data'));
    renderDonut(shell.querySelector('[data-donut="source"]'), readData('gccamp-source-data'));
  }

  function showTooltip(event) {
    const point = event.target.closest ? event.target.closest('.gc-point') : null;
    if (!point) return;
    const chart = point.closest('.ga-chart');
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
    const chart = event.target.closest('.ga-chart');
    const tooltip = chart && chart.querySelector('.gc-tooltip');
    if (tooltip) tooltip.hidden = true;
  }

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  async function refresh(options) {
    if (busy || !shell.dataset.dashboardUrl) return;
    busy = true;
    shell.classList.add('ga-loading');
    setStatus('Loading campaigns…', false);

    const params = new URLSearchParams(window.location.search);
    Object.entries(options || {}).forEach(([key, value]) => {
      if (key !== '_refresh') setParam(params, key, value);
    });

    if (params.get('range') === 'custom') {
      setParam(params, 'start', shell.querySelector('.gccamp-start-date')?.value || '');
      setParam(params, 'end', shell.querySelector('.gccamp-end-date')?.value || '');
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
      if (!response.ok) throw new Error('Campaign request failed');
      const payload = await response.json();
      shell.innerHTML = payload.html;
      const cleanParams = new URLSearchParams(params);
      cleanParams.delete('_');
      const query = cleanParams.toString();
      history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
      bindDashboard();
      renderCharts();
      updatePreview();
      setStatus('', false);
    } catch (error) {
      setStatus('Unable to refresh campaigns. Please try again.', true);
    } finally {
      busy = false;
      shell.classList.remove('ga-loading');
    }
  }

  function builderValue(name) {
    const field = shell.querySelector(`[data-builder="${name}"]`);
    return field ? String(field.value || '').trim() : '';
  }

  function updatePreview() {
    const box = shell.querySelector('[data-url-preview]');
    if (!box || !shell.querySelector('[data-builder]')) return;
    const destination = builderValue('destination');
    const values = {
      utm_source: builderValue('source'),
      utm_medium: builderValue('medium'),
      utm_campaign: builderValue('campaign'),
      utm_term: builderValue('term'),
      utm_content: builderValue('content'),
    };

    if (!destination) {
      box.innerHTML = '<code>Enter a destination URL to preview the trackable link.</code>';
      return;
    }

    let url;
    try {
      url = new URL(destination);
    } catch (error) {
      box.innerHTML = '<code>Enter a full http(s) URL.</code>';
      return;
    }
    if (!['http:', 'https:'].includes(url.protocol)) {
      box.innerHTML = '<code>Enter a full http(s) URL.</code>';
      return;
    }
    Object.entries(values).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    });
    box.innerHTML = `<code>${escapeHtml(url.toString())}</code>`;
  }

  function bindDashboard() {
    shell.querySelectorAll('.gccamp-refresh').forEach((button) => {
      button.onclick = () => refresh({ _refresh: true });
    });
    shell.querySelectorAll('[data-section]').forEach((button) => {
      button.onclick = (event) => {
        if (button.tagName === 'A') event.preventDefault();
        refresh({ section: button.dataset.section });
      };
    });
    const rangeSelect = shell.querySelector('.gccamp-range-select');
    if (rangeSelect) rangeSelect.onchange = () => refresh({ range: rangeSelect.value });
    const statusSelect = shell.querySelector('.gccamp-status-select');
    if (statusSelect) statusSelect.onchange = () => refresh({ status: statusSelect.value });
    const sortSelect = shell.querySelector('.gccamp-sort-select');
    if (sortSelect) sortSelect.onchange = () => refresh({ sort: sortSelect.value });
    const grainSelect = shell.querySelector('.gccamp-grain-select');
    if (grainSelect) grainSelect.onchange = () => refresh({ grain: grainSelect.value });
    const compare = shell.querySelector('.gccamp-compare');
    if (compare) compare.onchange = () => refresh({ compare: compare.checked ? '1' : '0' });
    const applyDate = shell.querySelector('.gccamp-date-apply');
    if (applyDate) applyDate.onclick = () => refresh({ _refresh: true });
    const reset = shell.querySelector('.gccamp-reset');
    if (reset) reset.onclick = () => {
      const params = new URLSearchParams();
      params.set('section', 'overview');
      history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
      refresh({ range: '7d', status: 'all', q: '', sort: 'created', grain: '', compare: '1', section: 'overview' });
    };
    const search = shell.querySelector('.gccamp-search-input');
    if (search) search.oninput = () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => refresh({ q: search.value }), 350);
    };
  }

  function bindBuilder() {
    shell.querySelectorAll('[data-builder]').forEach((field) => {
      field.addEventListener('input', updatePreview);
      field.addEventListener('change', updatePreview);
    });
    shell.querySelectorAll('.gccamp-preset').forEach((button) => {
      button.onclick = () => {
        const source = shell.querySelector('[data-builder="source"]');
        const medium = shell.querySelector('[data-builder="medium"]');
        if (source) source.value = button.dataset.templateSource || '';
        if (medium) medium.value = button.dataset.templateMedium || '';
        updatePreview();
      };
    });
    const resetBuilder = shell.querySelector('.gccamp-builder-reset');
    if (resetBuilder) resetBuilder.onclick = () => {
      shell.querySelectorAll('[data-builder]').forEach((field) => { field.value = ''; });
      const statusField = shell.querySelector('[data-builder="status"], select[name="status"]');
      if (statusField) statusField.value = 'Draft';
      updatePreview();
    };
    const copyPreview = shell.querySelector('[data-copy-preview]');
    if (copyPreview) copyPreview.onclick = () => {
      const box = shell.querySelector('[data-url-preview] code');
      copyText(box ? box.textContent.trim() : '');
    };
    const openPreview = shell.querySelector('[data-open-preview]');
    if (openPreview) openPreview.onclick = (event) => {
      const box = shell.querySelector('[data-url-preview] code');
      const value = box ? box.textContent.trim() : '';
      if (!value || /^Enter|^There/.test(value)) {
        event.preventDefault();
        setStatus('Build a valid URL before opening it.', true);
        return;
      }
      openPreview.href = value;
      openPreview.removeAttribute('aria-disabled');
    };
  }

  function bindCopyButtons() {
    shell.querySelectorAll('[data-copy-url]').forEach((button) => {
      button.onclick = () => copyText(button.dataset.copyUrl || '');
    });
  }

  function bindConfirmations() {
    document.querySelectorAll('form[data-confirm]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (!window.confirm(form.dataset.confirm || 'Are you sure?')) event.preventDefault();
      });
    });
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest && event.target.closest('.gc-point')) showTooltip(event);
  });
  document.addEventListener('mouseout', (event) => {
    if (event.target.closest && event.target.closest('.gc-point')) hideTooltip(event);
  });
  document.addEventListener('mouseover', (event) => {
    if (event.target.closest && event.target.closest('.gc-point')) showTooltip(event);
  });

  bindDashboard();
  bindBuilder();
  bindCopyButtons();
  bindConfirmations();
  renderCharts();
  updatePreview();

  const customRange = shell.querySelector('.gccamp-custom-range');
  if (customRange) {
    const rangeSelect = shell.querySelector('.gccamp-range-select');
    const syncCustomRange = () => { customRange.hidden = rangeSelect && rangeSelect.value !== 'custom'; };
    if (rangeSelect) rangeSelect.addEventListener('change', syncCustomRange);
    syncCustomRange();
  }
})();
