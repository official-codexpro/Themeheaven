(function () {
  const shell = document.getElementById('growth-social');
  const status = document.getElementById('gcsmm-status');
  if (!shell) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  let busy = false;
  let dragData = null;

  function element(name, attributes) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
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

  function readData(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function getCookie(name) {
    const parts = document.cookie ? document.cookie.split(';') : [];
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.startsWith(`${name}=`)) return decodeURIComponent(trimmed.slice(name.length + 1));
    }
    return '';
  }

  async function copyText(value) {
    if (!value) {
      setStatus('There is no text to copy yet.', true);
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
      setStatus('Copied to clipboard.', false);
    } catch (error) {
      setStatus('Unable to copy automatically. Copy the text manually.', true);
    }
  }

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  async function refresh(options) {
    if (busy || !shell.dataset.dashboardUrl) return;
    busy = true;
    shell.classList.add('ga-loading');
    setStatus('Loading social media workspace…', false);

    const params = new URLSearchParams(window.location.search);
    Object.entries(options || {}).forEach(([key, value]) => setParam(params, key, value));

    try {
      const response = await fetch(`${shell.dataset.dashboardUrl}?${params.toString()}`, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Social media request failed');
      const payload = await response.json();
      shell.innerHTML = payload.html;
      history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
      bind();
      renderCharts();
      updateTrackingPreview();
      setStatus('', false);
    } catch (error) {
      setStatus('Unable to refresh the workspace. Please try again.', true);
    } finally {
      busy = false;
      shell.classList.remove('ga-loading');
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
    const series = [
      { key: 'sessions', className: 'new' },
      { key: 'page_views', className: 'returning' },
    ];
    const values = series.flatMap((item) => data[item.key] || []);
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

    const labelStep = Math.max(1, Math.ceil(data.labels.length / 7));
    data.labels.forEach((label, index) => {
      if (index % labelStep !== 0 && index !== data.labels.length - 1) return;
      const x = padding.left + (data.labels.length === 1 ? plotWidth / 2 : (plotWidth * index) / (data.labels.length - 1));
      const text = element('text', {
        x: x,
        y: height - 10,
        'text-anchor': 'middle',
        class: 'gc-axis-label',
      });
      text.textContent = label;
      svg.appendChild(text);
    });

    series.forEach((item) => {
      const points = (data[item.key] || []).map((value, index) => {
        const x = padding.left + (data.labels.length === 1 ? plotWidth / 2 : (plotWidth * index) / (data.labels.length - 1));
        const y = padding.top + plotHeight - (Number(value) / maxValue) * plotHeight;
        return { x: x, y: y };
      });
      if (!points.length) return;
      svg.appendChild(element('path', {
        d: points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '),
        class: `gc-line gc-line-${item.className}`,
      }));
      points.forEach((point, index) => {
        svg.appendChild(element('circle', {
          cx: point.x,
          cy: point.y,
          r: 3,
          class: `gc-point gc-point-${item.className}`,
          'data-label': data.labels[index] || '',
          'data-series': item.key === 'sessions' ? 'Visits' : 'Page Views',
          'data-value': Number(data[item.key][index] || 0).toLocaleString(),
        }));
      });
    });
  }

  function renderCharts() {
    const data = readData('gcsmm-chart-data');
    renderLine(shell.querySelector('[data-chart="social-traffic"]'), data && data.traffic);
  }

  function updatePlatformPanels() {
    shell.querySelectorAll('[data-platform-toggle]').forEach((toggle) => {
      const panel = shell.querySelector(`[data-platform-panel="${toggle.value}"]`);
      if (panel) panel.hidden = !toggle.checked;
    });
  }

  function trackingValue(name) {
    const field = shell.querySelector(`[data-tracking="${name}"]`);
    return field ? String(field.value || '').trim() : '';
  }

  function updateTrackingPreview() {
    const box = shell.querySelector('[data-tracking-preview]');
    if (!box) return;
    const destination = trackingValue('destination');
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
    ['source', 'medium', 'campaign', 'term', 'content'].forEach((key) => {
      const value = trackingValue(key);
      if (value) url.searchParams.set(`utm_${key}`, value);
      else url.searchParams.delete(`utm_${key}`);
    });
    box.innerHTML = `<code>${escapeHtml(url.toString())}</code>`;
  }

  function dialog() {
    return document.getElementById('gcsmm-reschedule-dialog');
  }

  function closeDialog() {
    const panel = dialog();
    if (panel) panel.hidden = true;
    dragData = null;
  }

  async function saveReschedule(dateValue, timeValue) {
    if (!dragData || !dateValue || !timeValue) {
      setStatus('Choose both a date and a time.', true);
      return;
    }
    const form = new FormData();
    form.set('post_key', dragData.postKey);
    form.set('platform', dragData.platform);
    form.set('date', dateValue);
    form.set('time', timeValue);
    try {
      const response = await fetch(shell.dataset.rescheduleUrl || '/admin/growth-center/social/calendar/reschedule/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: form,
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'Reschedule failed');
      closeDialog();
      setStatus(`Reminder moved to ${payload.label}.`, false);
      await refresh({ _: String(Date.now()) });
    } catch (error) {
      setStatus(error.message || 'Unable to reschedule this reminder.', true);
    }
  }

  function bindCalendar() {
    shell.querySelectorAll('[data-calendar-nav]').forEach((button) => {
      button.onclick = () => refresh({ section: 'calendar', date: button.dataset.calendarNav });
    });

    shell.querySelectorAll('.gcsmm-calendar-entry').forEach((entry) => {
      entry.addEventListener('dragstart', () => {
        dragData = {
          postKey: entry.dataset.postKey,
          platform: entry.dataset.platform,
          time: entry.dataset.time,
        };
        entry.classList.add('is-dragging');
      });
      entry.addEventListener('dragend', () => {
        entry.classList.remove('is-dragging');
      });
    });

    shell.querySelectorAll('.gcsmm-calendar-day').forEach((day) => {
      day.addEventListener('dragover', (event) => {
        event.preventDefault();
        day.classList.add('is-drop-target');
      });
      day.addEventListener('dragleave', () => day.classList.remove('is-drop-target'));
      day.addEventListener('drop', (event) => {
        event.preventDefault();
        day.classList.remove('is-drop-target');
        if (!dragData) return;
        const panel = dialog();
        if (!panel) return;
        panel.hidden = false;
        const label = document.getElementById('gcsmm-reschedule-label');
        if (label) label.textContent = `${dragData.postKey} on ${dragData.platform}`;
        const dateField = document.getElementById('gcsmm-reschedule-date');
        const timeField = document.getElementById('gcsmm-reschedule-time');
        if (dateField) dateField.value = day.dataset.date || '';
        if (timeField) timeField.value = dragData.time || '09:00';
      });
    });

    const cancel = document.getElementById('gcsmm-reschedule-cancel');
    const save = document.getElementById('gcsmm-reschedule-save');
    if (cancel) cancel.onclick = closeDialog;
    if (save) {
      save.onclick = () => {
        const dateField = document.getElementById('gcsmm-reschedule-date');
        const timeField = document.getElementById('gcsmm-reschedule-time');
        saveReschedule(dateField ? dateField.value : '', timeField ? timeField.value : '');
      };
    }
  }

  function bind() {
    shell.querySelectorAll('[data-copy-text]').forEach((button) => {
      button.onclick = () => copyText(button.dataset.copyText || '');
    });

    shell.querySelectorAll('.gcsmm-refresh').forEach((button) => {
      button.onclick = () => refresh({ _: String(Date.now()) });
    });

    shell.querySelectorAll('[data-section]').forEach((link) => {
      link.onclick = (event) => {
        if (link.tagName === 'A') event.preventDefault();
        refresh({ section: link.dataset.section });
      };
    });

    shell.querySelectorAll('[data-platform-toggle]').forEach((toggle) => {
      toggle.onchange = updatePlatformPanels;
    });
    updatePlatformPanels();

    shell.querySelectorAll('[data-workflow-submit]').forEach((button) => {
      button.onclick = () => {
        const hidden = shell.querySelector('input[name="workflow_action"]');
        if (hidden) hidden.value = button.dataset.workflowSubmit;
      };
    });

    shell.querySelectorAll('[data-tracking]').forEach((field) => {
      field.addEventListener('input', updateTrackingPreview);
      field.addEventListener('change', updateTrackingPreview);
    });
    updateTrackingPreview();

    bindCalendar();
  }

  bind();
  renderCharts();
})();
