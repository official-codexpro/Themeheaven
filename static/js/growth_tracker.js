(function () {
  var configNode = document.getElementById('growth-analytics-config');
  if (!configNode) return;

  var config;
  try {
    config = JSON.parse(configNode.textContent);
  } catch (error) {
    return;
  }
  if (!config || !config.enabled || !config.endpoint || !config.token) return;

  var startedAt = Date.now();
  var sent = false;
  var sentConversions = {};
  var elementCounter = 0;
  var conversionConfig = config.conversion || { endpoint: '/analytics/conversion/', rules: [] };

  function payload() {
    var values = new URLSearchParams();
    values.set('token', config.token);
    values.set('csrfmiddlewaretoken', config.csrfToken || '');
    values.set('duration_ms', String(Math.max(0, Date.now() - startedAt)));
    values.set('path', config.path || window.location.pathname);
    return values;
  }

  function send() {
    if (sent) return;
    sent = true;
    var body = payload();
    if (navigator.sendBeacon) {
      navigator.sendBeacon(config.endpoint, body);
      return;
    }
    fetch(config.endpoint, {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      keepalive: true,
    }).catch(function () {});
  }

  function conversionPayload(detail) {
    var values = new URLSearchParams();
    values.set('token', config.token);
    values.set('csrfmiddlewaretoken', config.csrfToken || '');
    values.set('event_name', detail.name);
    values.set('event_type', detail.type || 'cta_click');
    values.set('path', detail.path || window.location.pathname);
    values.set('source', detail.source || '');
    values.set('goal_key', detail.goal || '');
    values.set('dedupe_key', detail.dedupeKey || detail.name);
    return values;
  }

  function sendConversion(detail) {
    if (!detail.name || !conversionConfig.endpoint) return;
    if (sentConversions[detail.dedupeKey]) return;
    sentConversions[detail.dedupeKey] = true;
    fetch(conversionConfig.endpoint, {
      method: 'POST',
      body: conversionPayload(detail),
      credentials: 'same-origin',
      keepalive: true,
    }).catch(function () {});
  }

  function matchingRule(element) {
    var rules = conversionConfig.rules || [];
    for (var i = 0; i < rules.length; i += 1) {
      try {
        if (element.matches(rules[i].selector)) return rules[i];
      } catch (error) {
        continue;
      }
    }
    return null;
  }

  function elementKey(element) {
    if (!element.dataset.conversionId) {
      elementCounter += 1;
      element.dataset.conversionId = 'el-' + elementCounter;
    }
    return element.dataset.conversionId;
  }

  document.addEventListener('click', function (event) {
    var element = event.target.closest('[data-track-event], a, button');
    if (!element) return;
    var rule = matchingRule(element);
    var name = element.dataset.trackEvent || (rule && rule.eventName) || '';
    if (!name) return;
    var type = element.dataset.trackType || (rule && rule.eventType) || 'cta_click';
    var goal = element.dataset.trackGoal || (rule && rule.goalKey) || '';
    var path = element.dataset.trackPath || (rule && rule.path) || window.location.pathname;
    var source = element.dataset.trackName || (element.innerText || element.textContent || '').trim().slice(0, 120);
    var dedupeKey = [name, type, path, elementKey(element)].join('|');
    sendConversion({ name: name, type: type, goal: goal, path: path, source: source, dedupeKey: dedupeKey });
  });

  window.addEventListener('pagehide', function (event) {
    if (!event.persisted) send();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') send();
  });
})();
