(function () {
  const root = document.getElementById('seo-settings');
  if (!root) return;

  const configNode = document.getElementById('gcseo-config');
  const config = configNode ? JSON.parse(configNode.textContent) : {};
  const form = root.querySelector('[data-seo-form]');
  const resetInput = root.querySelector('[data-reset-input]');
  let fileDirty = false;
  let previewUrl = '';

  const find = (selector) => root.querySelector(selector);

  function truncate(value, limit) {
    const text = String(value || '').trim();
    return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
  }

  function normalizeDomain(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const parsed = new URL(raw.includes('://') ? raw : `https://${raw}`);
    return parsed.hostname.toLowerCase();
  }

  function replaceHost(url, domain) {
    if (!url || !domain) return url;
    try {
      const parsed = new URL(url);
      parsed.host = domain;
      return parsed.toString().replace(/\/$/, '') + (parsed.pathname === '/' ? '' : '');
    } catch (error) {
      return url;
    }
  }

  function updateCounter(name, input, min, max) {
    if (!input) return;
    const wrapper = root.querySelector(`[data-counter-for="${name}"]`);
    if (!wrapper) return;
    const current = wrapper.querySelector('[data-current]');
    const length = input.value.trim().length;
    current.textContent = String(length);
    wrapper.classList.toggle('is-warning', length < min || length > max);
    wrapper.classList.toggle('is-invalid', length > max + 40);
  }

  function updatePreview() {
    const titleInput = root.querySelector('[name="seo_title"]');
    const descriptionInput = root.querySelector('[name="meta_description"]');
    const domainInput = root.querySelector('[name="primary_domain"]');
    const tokenInput = root.querySelector('[data-verification-input]');

    updateCounter('title', titleInput, 30, 60);
    updateCounter('description', descriptionInput, 120, 160);

    const domain = normalizeDomain(domainInput && domainInput.value) || config.domain || '';
    const title = truncate(
      titleInput && titleInput.value.trim() ? titleInput.value : config.safeTitle,
      60,
    );
    const description = truncate(
      descriptionInput && descriptionInput.value.trim() ? descriptionInput.value : config.safeDescription,
      160,
    );

    const domainNode = find('[data-preview-domain]');
    const titleNode = find('[data-preview-title]');
    const descriptionNode = find('[data-preview-description]');
    if (domainNode) domainNode.textContent = domain;
    if (titleNode) titleNode.textContent = title;
    if (descriptionNode) descriptionNode.textContent = description;

    if (tokenInput) {
      const tokenNode = find('.gcseo-token-preview');
      if (tokenNode) tokenNode.textContent = `<meta name="google-site-verification" content="${tokenInput.value.trim()}" />`;
    }

    const indexInput = root.querySelector('[name="index_enabled"]');
    const status = find('[data-visibility-status]');
    if (status && indexInput) status.textContent = indexInput.checked ? 'Indexing enabled' : 'Global noindex';
  }

  function updateRobotsPreview() {
    const editor = root.querySelector('[data-robots-editor]');
    const enabled = root.querySelector('[name="robots_txt_enabled"]');
    const sitemapEnabled = root.querySelector('[name="sitemap_enabled"]');
    const preview = find('[data-robots-preview]');
    if (!editor || !preview) return;

    let content = enabled && !enabled.checked ? config.safeRobots : editor.value.trim();
    if (!content) content = config.safeRobots;

    if (sitemapEnabled && sitemapEnabled.checked) {
      const domainInput = root.querySelector('[name="primary_domain"]');
      const sitemapUrl = replaceHost(config.sitemapUrl, normalizeDomain(domainInput && domainInput.value));
      const sitemapLine = `Sitemap: ${sitemapUrl}`;
      if (!content.split('\n').some((line) => line.trim().toLowerCase().startsWith('sitemap:'))) {
        content = `${content}\n\n${sitemapLine}`;
      }
    }

    preview.textContent = `${content.trim()}\n`;
  }

  function updateImagePreview() {
    const fileInput = root.querySelector('[name="default_image"]');
    const removeInput = root.querySelector('[name="remove_default_image"]');
    const image = find('[data-image-preview]');
    if (!fileInput || !image) return;

    if (removeInput && removeInput.checked) {
      image.src = config.faviconUrl || '';
      return;
    }
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    image.src = previewUrl;
  }

  function snapshot() {
    if (!form) return '';
    const data = new FormData(form);
    data.delete('reset');
    data.delete('default_image');
    return Array.from(data.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => `${key}=${value}`)
      .join('|');
  }

  const initialSnapshot = snapshot();

  function setDirty(dirty) {
    [find('[data-dirty-state]'), find('[data-footer-dirty-state]')].forEach((node) => {
      if (node) node.hidden = !dirty;
    });
  }

  function updateDirty() {
    setDirty(fileDirty || snapshot() !== initialSnapshot);
  }

  root.addEventListener('input', (event) => {
    updatePreview();
    updateRobotsPreview();
    updateDirty();
    if (event.target && event.target.matches('[name="google_verification_token"]')) {
      const tokenNode = find('.gcseo-token-preview');
      if (tokenNode) tokenNode.textContent = `<meta name="google-site-verification" content="${event.target.value.trim()}" />`;
    }
  });

  root.addEventListener('change', (event) => {
    if (event.target && event.target.matches('[name="default_image"]')) fileDirty = true;
    updatePreview();
    updateRobotsPreview();
    updateImagePreview();
    updateDirty();
  });

  root.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-seo-tab]');
    if (tab) {
      root.querySelectorAll('[data-seo-tab]').forEach((node) => {
        node.classList.toggle('is-active', node === tab);
        node.setAttribute('aria-selected', node === tab ? 'true' : 'false');
      });
      root.querySelectorAll('[data-seo-panel]').forEach((panel) => {
        panel.classList.toggle('is-active', panel.dataset.seoPanel === tab.dataset.seoTab);
      });
      return;
    }

    if (event.target.closest('[data-robots-default]')) {
      const editor = root.querySelector('[data-robots-editor]');
      if (editor) {
        editor.value = config.safeRobots;
        updateRobotsPreview();
        updateDirty();
      }
      return;
    }

    if (event.target.closest('[data-reset-button]')) {
      const confirmed = window.confirm('Reset all SEO settings to safe defaults? Analytics, content, and unrelated uploads will not be deleted.');
      if (!confirmed) return;
      if (resetInput) resetInput.hidden = false;
      if (form) form.submit();
    }
  });

  if (form) {
    form.addEventListener('submit', () => setDirty(false));
  }

  window.addEventListener('beforeunload', (event) => {
    if (fileDirty || snapshot() !== initialSnapshot) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  updatePreview();
  updateRobotsPreview();
})();
