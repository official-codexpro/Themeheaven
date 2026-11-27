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

  window.addEventListener('pagehide', function (event) {
    if (!event.persisted) send();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') send();
  });
})();
