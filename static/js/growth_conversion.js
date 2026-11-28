(function () {
  const shell = document.getElementById('growth-conversion');
  if (!shell) return;

  const status = document.getElementById('gct-status');
  let busy = false;

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

  function setParam(params, key, value) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }

  async function refresh(url) {
    if (busy || !shell.dataset.dashboardUrl) return;
    busy = true;
    shell.classList.add('ga-loading');
    setStatus('Loading conversion data…', false);

    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Conversion request failed');
      const payload = await response.json();
      const container = document.getElementById('growth-conversion-content');
      if (container) container.innerHTML = payload.html;
      history.replaceState(null, '', url);
      bindDynamic();
      setStatus('', false);
    } catch (error) {
      setStatus('Unable to refresh conversion data. Please try again.', true);
    } finally {
      busy = false;
      shell.classList.remove('ga-loading');
    }
  }

  function sectionUrl(section) {
    const params = new URLSearchParams(window.location.search);
    setParam(params, 'section', section);
    return `${window.location.pathname}?${params.toString()}`;
  }

  function bindDynamic() {
    shell.querySelectorAll('[data-section]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        event.preventDefault();
        refresh(sectionUrl(link.dataset.section));
      });
    });

    const form = shell.querySelector('[data-filter-form]');
    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        const params = new URLSearchParams(new FormData(form));
        refresh(`${window.location.pathname}?${params.toString()}`);
      });
    }

    shell.querySelectorAll('.gct-pagination a').forEach(function (link) {
      link.addEventListener('click', function (event) {
        event.preventDefault();
        refresh(link.href);
      });
    });

    const refreshLink = shell.querySelector('[data-refresh]');
    if (refreshLink) {
      refreshLink.addEventListener('click', function (event) {
        event.preventDefault();
        refresh(window.location.href);
      });
    }
  }

  bindDynamic();
})();
