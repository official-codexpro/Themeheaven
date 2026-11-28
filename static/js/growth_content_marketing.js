(function () {
  const shell = document.getElementById('growth-content-marketing');
  if (!shell) return;

  const status = document.getElementById('gcm-status');
  let busy = false;
  let dragData = null;

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

  function getCookie(name) {
    const parts = document.cookie ? document.cookie.split(';') : [];
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.startsWith(`${name}=`)) return decodeURIComponent(trimmed.slice(name.length + 1));
    }
    return '';
  }

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  function readJson(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function slugify(value) {
    return String(value || '')
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  async function refresh(options, form) {
    if (busy || !shell.dataset.dashboardUrl) return;
    busy = true;
    shell.classList.add('ga-loading');
    setStatus('Loading content workspace…', false);

    const params = form ? new URLSearchParams(new FormData(form)) : new URLSearchParams(window.location.search);
    Object.entries(options || {}).forEach(([key, value]) => setParam(params, key, value));

    try {
      const response = await fetch(`${shell.dataset.dashboardUrl}?${params.toString()}`, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Content request failed');
      const payload = await response.json();
      const container = document.getElementById('growth-content-marketing-content');
      if (container) container.innerHTML = payload.html;
      history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
      bindDynamic();
      renderTraffic();
      setStatus('', false);
    } catch (error) {
      setStatus('Unable to refresh the content workspace. Please try again.', true);
    } finally {
      busy = false;
      shell.classList.remove('ga-loading');
    }
  }

  function renderTraffic() {
    const data = readJson('gcm-traffic-data');
    const target = shell.querySelector('[data-traffic-bars]');
    if (!data || !target || !Array.isArray(data.labels)) return;

    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    const visitors = Array.isArray(data.visitors) ? data.visitors : [];
    const views = Array.isArray(data.page_views) ? data.page_views : [];
    const maximum = Math.max(1, ...sessions, ...visitors, ...views);
    target.textContent = '';

    if (!data.labels.length) {
      const empty = document.createElement('p');
      empty.className = 'gcm-muted';
      empty.textContent = 'No traffic recorded for this date range.';
      target.appendChild(empty);
      return;
    }

    data.labels.forEach((label, index) => {
      const column = document.createElement('div');
      column.className = 'gcm-bar-column';
      const stack = document.createElement('div');
      stack.className = 'gcm-bar-stack';
      [
        ['sessions', sessions, 'Sessions'],
        ['visitors', visitors, 'Visitors'],
        ['views', views, 'Page views'],
      ].forEach(([key, series, title]) => {
        const value = Number(series[index] || 0);
        const bar = document.createElement('i');
        bar.className = `gcm-bar gcm-bar-${key}`;
        bar.style.height = `${value ? Math.max(2, (value / maximum) * 100) : 0}%`;
        bar.title = `${title}: ${value.toLocaleString()}`;
        stack.appendChild(bar);
      });
      const caption = document.createElement('span');
      caption.className = 'gcm-bar-label';
      caption.textContent = label;
      column.appendChild(stack);
      column.appendChild(caption);
      target.appendChild(column);
    });
  }

  async function reschedule(key, date) {
    const url = shell.dataset.rescheduleUrl;
    if (!url || !key || !date) {
      setStatus('Choose a valid date to reschedule this content.', true);
      return;
    }
    setStatus('Moving content…', false);
    const form = new FormData();
    form.set('key', key);
    form.set('date', date);
    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: form,
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'Unable to reschedule content.');
      await refresh({ _: String(Date.now()) });
      setStatus(`Moved ${payload.key} to ${payload.date}.`, false);
    } catch (error) {
      setStatus(error.message || 'Unable to reschedule this content.', true);
    }
  }

  function bindCalendar() {
    shell.querySelectorAll('.gcm-calendar-entry[data-key]').forEach((card) => {
      if (!card.draggable || card.dataset.gcmBound) return;
      card.dataset.gcmBound = '1';
      card.addEventListener('dragstart', (event) => {
        dragData = { key: card.dataset.key };
        card.classList.add('is-dragging');
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', card.dataset.key);
        }
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('is-dragging');
        dragData = null;
      });
    });

    shell.querySelectorAll('[data-date]').forEach((cell) => {
      if (!cell.classList.contains('gcm-calendar-day') && !cell.classList.contains('gcm-list-row')) return;
      if (cell.dataset.gcmDropBound) return;
      cell.dataset.gcmDropBound = '1';
      cell.addEventListener('dragover', (event) => {
        if (!dragData) return;
        event.preventDefault();
        cell.classList.add('is-drop-target');
        if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      });
      cell.addEventListener('dragleave', () => cell.classList.remove('is-drop-target'));
      cell.addEventListener('drop', (event) => {
        event.preventDefault();
        cell.classList.remove('is-drop-target');
        if (!dragData) return;
        const key = dragData.key;
        dragData = null;
        reschedule(key, cell.dataset.date);
      });
    });
  }

  function bindDynamic() {
    const form = shell.querySelector('[data-filter-form]');
    if (form && !form.dataset.gcmBound) {
      form.dataset.gcmBound = '1';
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        refresh({}, form);
      });
    }

    shell.querySelectorAll('[data-section]').forEach((link) => {
      if (link.dataset.gcmBound) return;
      link.dataset.gcmBound = '1';
      link.addEventListener('click', (event) => {
        event.preventDefault();
        refresh({ section: link.dataset.section, page: null });
      });
    });

    shell.querySelectorAll('[data-refresh]').forEach((link) => {
      if (link.dataset.gcmBound) return;
      link.dataset.gcmBound = '1';
      link.addEventListener('click', (event) => {
        event.preventDefault();
        refresh({ _: String(Date.now()) });
      });
    });

    shell.querySelectorAll('[data-calendar-nav]').forEach((link) => {
      if (link.dataset.gcmBound) return;
      link.dataset.gcmBound = '1';
      link.addEventListener('click', (event) => {
        event.preventDefault();
        refresh({ section: 'calendar', date: link.dataset.calendarNav });
      });
    });

    shell.querySelectorAll('[data-calendar-view]').forEach((link) => {
      if (link.dataset.gcmBound) return;
      link.dataset.gcmBound = '1';
      link.addEventListener('click', (event) => {
        event.preventDefault();
        refresh({ section: 'calendar', view: link.dataset.calendarView });
      });
    });

    shell.querySelectorAll('[data-page]').forEach((link) => {
      if (link.dataset.gcmBound) return;
      link.dataset.gcmBound = '1';
      link.addEventListener('click', (event) => {
        event.preventDefault();
        refresh({ page: link.dataset.page });
      });
    });

    bindCalendar();
  }

  function bindEditor() {
    const editor = shell.querySelector('[data-content-editor]');
    const preview = shell.querySelector('[data-content-preview]');
    if (editor && preview) {
      editor.addEventListener('input', renderPreview);
      renderPreview();
    }

    const source = shell.querySelector('[data-slug-source]');
    const slug = shell.querySelector('input[name="slug"]');
    if (source && slug && !String(slug.value || '').trim()) {
      source.addEventListener('input', () => {
        if (!String(slug.value || '').trim()) slug.value = slugify(source.value);
      });
    }
  }

  function renderPreview() {
    const editor = shell.querySelector('[data-content-editor]');
    const preview = shell.querySelector('[data-content-preview]');
    if (!editor || !preview) return;
    const blocks = String(editor.value || '')
      .split(/\n\s*\n/)
      .map((block) => block.trim())
      .filter(Boolean);
    preview.textContent = '';
    if (!blocks.length) {
      const empty = document.createElement('p');
      empty.textContent = 'Nothing to preview yet. Start writing in the body field.';
      preview.appendChild(empty);
      return;
    }
    blocks.forEach((block) => {
      const paragraph = document.createElement('p');
      paragraph.textContent = block;
      preview.appendChild(paragraph);
    });
  }

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (form.dataset.gcmConfirmed === '1') {
      form.dataset.gcmConfirmed = '';
      return;
    }
    const trigger = form.querySelector('[data-confirm]');
    if (!trigger) return;
    event.preventDefault();
    const message = trigger.dataset.confirm || 'Are you sure?';
    if (!window.confirm(message)) return;
    form.dataset.gcmConfirmed = '1';
    if (typeof form.requestSubmit === 'function') form.requestSubmit(trigger);
    else trigger.click();
  });

  bindDynamic();
  bindEditor();
  renderTraffic();
})();
