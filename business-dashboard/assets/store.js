/* Data layer.
 *
 * One entry point for both run modes. The page always talks to Store; Store
 * decides whether that means HTTP to the local service or localStorage.
 *
 * Plain <script>, no modules: file:// would refuse an ES module.
 */
(function (window) {
  'use strict';

  var CACHE_KEY = 'biz_project_board_cache_v1';
  var LEGACY_KEY = 'biz_project_board_v4';

  var Store = {
    mode: 'offline',
    info: null,
    lastError: ''
  };

  function stamp() {
    return 'id' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  function request(path, options) {
    var config = options || {};
    config.headers = { 'Content-Type': 'application/json' };
    config.cache = 'no-store';
    return fetch(path, config).then(function (response) {
      if (response.ok) return response.json();
      return response.json().catch(function () { return null; }).then(function (body) {
        var detail = body && (body.detail || (body.error && body.error.message));
        if (Array.isArray(detail)) {
          detail = detail.map(function (item) { return item.msg; }).join('；');
        }
        throw new Error(detail || ('请求失败 ' + response.status));
      });
    });
  }

  Store.detect = function () {
    if (location.protocol === 'file:') {
      Store.mode = 'offline';
      return Promise.resolve(null);
    }
    return request('/api/health').then(function (info) {
      Store.mode = 'backend';
      Store.info = info;
      return info;
    }).catch(function () {
      Store.mode = 'offline';
      Store.info = null;
      return null;
    });
  };

  Store.load = function () {
    if (Store.mode !== 'backend') return Promise.resolve(null);
    return request('/api/bootstrap');
  };

  var queued = null;
  var pushing = false;
  var timer = null;

  function flush() {
    if (pushing || !queued) return;
    var payload = queued;
    queued = null;
    pushing = true;
    request('/api/state', { method: 'POST', body: JSON.stringify(payload) })
      .catch(function (error) {
        Store.lastError = error.message;
        if (typeof window.onBackendLost === 'function') window.onBackendLost(error);
      })
      .then(function () {
        pushing = false;
        if (queued) flush();
      });
  }

  Store.push = function (db) {
    if (Store.mode !== 'backend') return;
    queued = {
      customers: db.customers || [],
      projects: db.projects || [],
      phases: db.phases || []
    };
    if (timer) clearTimeout(timer);
    timer = setTimeout(flush, 220);
  };

  Store.flushNow = function () {
    if (timer) clearTimeout(timer);
    flush();
  };

  Store.cached = function () {
    try {
      var raw = localStorage.getItem(CACHE_KEY) || localStorage.getItem(LEGACY_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || !Array.isArray(data.projects)) return null;
      return data;
    } catch (error) {
      return null;
    }
  };

  Store.cache = function (db) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        customers: db.customers || [],
        projects: db.projects || [],
        phases: db.phases || []
      }));
    } catch (error) {
      Store.lastError = '浏览器拒绝写入本地缓存，请务必导出备份';
    }
  };

  Store.parse = function (text) {
    if (Store.mode === 'backend') {
      return request('/api/parse', { method: 'POST', body: JSON.stringify({ text: text }) });
    }
    var fallback = window.LocalParse
      ? window.LocalParse.parse(text, window.DB.customers, window.DB.phases)
      : null;
    return Promise.resolve(fallback);
  };

  /* Turn a ParseResult into the flat object the existing preview panel expects,
   * so that renderPreview/confirmParse keep working untouched. */
  Store.toPending = function (result) {
    if (!result) return null;
    var fields = result.fields || {};
    var pending = {
      name: '', customer: '', phase: '', start: '', end: '', contact: '', dept: '',
      deptType: '', contactWay: '', means: '', channel: '', note: '', next: '',
      updated: new Date().toISOString().slice(0, 10),
      unsure: result.unresolved ? result.unresolved.slice() : [],
      done: result.done_phases || [],
      milestones: [], msDate: '', msLabel: '', newCustomer: ''
    };
    Object.keys(fields).forEach(function (key) {
      if (key === 'updated') return;
      pending[key] = fields[key].value || '';
    });

    var customer = fields.customer || {};
    if (customer.is_new && customer.suggest_name) pending.newCustomer = customer.suggest_name;

    var milestones = (result.milestones || []).map(function (item) {
      return { id: stamp(), date: item.date, label: item.label || '关键时间点' };
    });
    pending.milestones = milestones;
    if (milestones.length) {
      pending.msDate = milestones[0].date;
      pending.msLabel = milestones[0].label;
    } else {
      pending.unsure = pending.unsure.concat(['msDate']);
    }
    pending.parser = result.parser || '本地规则';
    pending.warnings = result.warnings || [];
    pending.text = result.text || '';
    pending._raw = result;
    return pending;
  };

  Store.exportPayload = function (db) {
    return {
      format: 'bizboard',
      version: 1,
      exported_at: new Date().toISOString(),
      data: {
        customers: db.customers || [],
        projects: db.projects || [],
        phases: db.phases || []
      }
    };
  };

  Store.importFile = function (file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var parsed = JSON.parse(reader.result);
          var data = parsed && parsed.data ? parsed.data : parsed;
          if (!data || (!data.projects && !data.customers && !data.phases)) {
            reject(new Error('这个文件里没有项目数据'));
            return;
          }
          resolve(data);
        } catch (error) {
          reject(new Error('文件不是合法的 JSON'));
        }
      };
      reader.onerror = function () { reject(new Error('读不到这个文件')); };
      reader.readAsText(file, 'utf-8');
    });
  };

  Store.getProvider = function () {
    if (Store.mode !== 'backend') {
      return Promise.reject(new Error('离线模式下没有模型配置，请先用后端模式启动'));
    }
    return request('/api/provider');
  };

  Store.saveProvider = function (payload) {
    if (Store.mode !== 'backend') {
      return Promise.reject(new Error('离线模式下没有模型配置'));
    }
    return request('/api/provider', { method: 'PUT', body: JSON.stringify(payload) });
  };

  Store.testProvider = function (payload) {
    if (Store.mode !== 'backend') {
      return Promise.reject(new Error('离线模式下无法测试连接'));
    }
    return request('/api/provider/test', {
      method: 'POST', body: JSON.stringify(payload || {})
    });
  };

  Store.clearKey = function (current) {
    var payload = {
      enabled: false, provider: current.provider, base_url: current.base_url,
      model: current.model, json_mode: current.json_mode, api_key: ''
    };
    return Store.saveProvider(payload);
  };

  window.Store = Store;
})(window);
