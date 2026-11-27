(function () {
  'use strict';

  var configNode = document.getElementById('page-seo-config');
  var config = {};
  if (configNode) {
    try {
      config = JSON.parse(configNode.textContent);
    } catch (error) {
      config = {};
    }
  }

  var bulkForm = document.querySelector('[data-bulk-form]');
  if (bulkForm) {
    var selects = Array.prototype.slice.call(bulkForm.querySelectorAll('[data-page-select]'));
    var confirmBox = bulkForm.querySelector('[data-bulk-confirm]');
    var submit = bulkForm.querySelector('[data-bulk-submit]');

    function updateBulkState() {
      var selected = selects.some(function (input) { return input.checked; });
      submit.disabled = !selected || !confirmBox.checked;
    }

    selects.forEach(function (input) {
      input.addEventListener('change', updateBulkState);
    });
    confirmBox.addEventListener('change', updateBulkState);
    updateBulkState();
  }

  var editor = document.querySelector('[data-page-editor]');
  if (!editor) {
    return;
  }

  var form = editor.querySelector('[data-page-form]');
  var dirtyState = editor.querySelector('[data-dirty-state]');
  var defaults = {
    title: config.defaultTitle || config.safeTitle || '',
    description: config.defaultDescription || config.safeDescription || '',
    url: config.generatedCanonical || ''
  };

  function markDirty() {
    if (dirtyState) {
      dirtyState.hidden = false;
    }
  }

  form.addEventListener('input', markDirty);
  form.addEventListener('change', markDirty);

  function valueOf(selector) {
    var node = form.querySelector(selector);
    return node ? String(node.value || '').trim() : '';
  }

  function setText(selector, value) {
    var node = editor.querySelector(selector);
    if (node) {
      node.textContent = value || '';
    }
  }

  function updateCounter(key, value) {
    var counter = editor.querySelector('[data-page-counter-for="' + key + '"]');
    var countNode = editor.querySelector('[data-page-count="' + key + '"]');
    if (countNode) {
      countNode.textContent = String(value.length);
    }
    if (counter) {
      var recommended = key === 'title' ? [30, 60] : [120, 320];
      counter.classList.toggle('gcpage-counter-warning', value.length > 0 && (value.length < recommended[0] || value.length > recommended[1]));
    }
  }

  function updateBadge(source, isCustom, customLabel, inheritedLabel) {
    editor.querySelectorAll('[data-page-source="' + source + '"]').forEach(function (node) {
      node.textContent = isCustom ? customLabel : inheritedLabel;
      node.classList.remove('gcpage-badge-custom', 'gcpage-badge-inherited', 'gcpage-badge-good');
      node.classList.add(isCustom ? 'gcpage-badge-custom' : 'gcpage-badge-inherited');
    });
  }

  var socialImage = editor.querySelector('[data-social-image]');
  var socialPlaceholder = editor.querySelector('[data-social-placeholder]');
  var initialImageSrc = socialImage ? socialImage.getAttribute('src') || '' : '';
  var objectUrl = '';

  function updateSocialImage() {
    if (!socialImage || !socialPlaceholder) {
      return;
    }
    var remove = form.querySelector('[data-page-remove-image]');
    var fileInput = form.querySelector('[data-page-og] [data-page-og="image"]') || form.querySelector('input[type="file"][data-page-og="image"]');
    var file = fileInput && fileInput.files && fileInput.files[0];

    if (remove && remove.checked) {
      socialImage.hidden = true;
      socialPlaceholder.hidden = false;
      return;
    }

    if (file) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
      objectUrl = URL.createObjectURL(file);
      socialImage.src = objectUrl;
      socialImage.hidden = false;
      socialPlaceholder.hidden = true;
      return;
    }

    socialImage.src = initialImageSrc;
    socialImage.hidden = !initialImageSrc;
    socialPlaceholder.hidden = Boolean(initialImageSrc);
  }

  function updatePreviews() {
    var title = valueOf('[data-page-counter="title"]') || defaults.title;
    var description = valueOf('[data-page-counter="description"]') || defaults.description;
    var canonicalField = form.querySelector('[name="canonical_override"]');
    var resetCanonical = form.querySelector('[data-reset-canonical]');
    if (canonicalField) {
      canonicalField.disabled = Boolean(resetCanonical && resetCanonical.checked);
    }
    var canonical = (resetCanonical && resetCanonical.checked)
      ? defaults.url
      : (valueOf('[name="canonical_override"]') || defaults.url);

    updateCounter('title', valueOf('[data-page-counter="title"]'));
    updateCounter('description', valueOf('[data-page-counter="description"]'));
    setText('[data-search-title]', title);
    setText('[data-search-description]', description);
    setText('[data-search-url]', canonical);
    setText('[data-social-url]', canonical);

    var ogTitle = valueOf('[data-page-og="title"]') || valueOf('[data-page-counter="title"]') || defaults.title;
    var ogDescription = valueOf('[data-page-og="description"]') || valueOf('[data-page-counter="description"]') || defaults.description;
    setText('[data-social-title]', ogTitle);
    setText('[data-social-description]', ogDescription);

    updateBadge('title', Boolean(valueOf('[data-page-counter="title"]')), 'Custom title', 'Inherited title');
    updateBadge('description', Boolean(valueOf('[data-page-counter="description"]')), 'Custom description', 'Inherited description');
    updateBadge('image', Boolean(valueOf('[name="og_image"]')), 'Custom image', 'Inherited image');
  }

  var schemaPreview = editor.querySelector('[data-schema-preview]');
  var schemaError = editor.querySelector('[data-schema-error]');

  function updateSchemaPreview() {
    var mode = valueOf('[data-page-schema-mode]') || 'inherit';
    var type = valueOf('[data-page-schema-type]') || 'webpage';
    var custom = valueOf('[data-page-schema-json]');
    var payload = {};

    if (schemaError) {
      schemaError.hidden = true;
      schemaError.textContent = '';
    }

    if (mode === 'custom') {
      if (!custom) {
        if (schemaPreview) {
          schemaPreview.textContent = '';
        }
        if (schemaError) {
          schemaError.textContent = 'Enter valid JSON to preview custom structured data.';
          schemaError.hidden = false;
        }
        return;
      }
      try {
        payload = JSON.parse(custom);
      } catch (error) {
        if (schemaPreview) {
          schemaPreview.textContent = '';
        }
        if (schemaError) {
          schemaError.textContent = 'Invalid JSON: ' + error.message;
          schemaError.hidden = false;
        }
        return;
      }
    } else if (mode === 'generated') {
      payload = {
        '@context': 'https://schema.org',
        '@type': type === 'product' ? 'Product' : 'WebPage',
        '@id': valueOf('[name="canonical_override"]') || defaults.url,
        'name': valueOf('[data-page-counter="title"]') || defaults.title,
        'url': valueOf('[name="canonical_override"]') || defaults.url
      };
    }

    if (schemaPreview) {
      schemaPreview.textContent = Object.keys(payload).length ? JSON.stringify(payload, null, 2) : '{}';
    }
  }

  form.addEventListener('input', function (event) {
    updatePreviews();
    if (event.target && event.target.matches('[data-page-schema-json], [data-page-schema-mode], [data-page-schema-type]')) {
      updateSchemaPreview();
    }
    if (event.target && event.target.matches('[data-page-og="image"]')) {
      updateSocialImage();
    }
  });

  form.addEventListener('change', function (event) {
    updatePreviews();
    updateSchemaPreview();
    updateSocialImage();
    if (event.target && event.target.matches('[data-page-schema-mode]')) {
      var customField = form.querySelector('[data-page-schema-json]');
      if (customField) {
        customField.disabled = valueOf('[data-page-schema-mode]') !== 'custom';
      }
    }
  });

  var schemaModeField = form.querySelector('[data-page-schema-mode]');
  var customSchemaField = form.querySelector('[data-page-schema-json]');
  if (schemaModeField && customSchemaField) {
    customSchemaField.disabled = valueOf('[data-page-schema-mode]') !== 'custom';
  }

  updatePreviews();
  updateSchemaPreview();
  updateSocialImage();
})();
