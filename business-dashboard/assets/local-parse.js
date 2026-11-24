/* Offline parsing.
 *
 * Same rules as app/parsing/local_rules.py so that a sentence typed in offline
 * mode produces the same fields it would with the service running. Keep the
 * two in sync: change one, change the other.
 */
(function (window) {
  'use strict';

  var WEEKDAY = { '一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6 };
  var FIELDS = ['name', 'customer', 'phase', 'start', 'end', 'contact', 'dept',
    'deptType', 'contactWay', 'means', 'channel', 'note', 'next', 'updated'];

  var PATTERNS = [
    { name: 'abs', re: /20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*[日号]?/g },
    { name: 'cn', re: /\d{1,2}\s*月\s*\d{1,2}\s*[日号]/g },
    { name: 'cnmonth', re: /\d{1,2}\s*月(?:底|初|中)/g },
    { name: 'md', re: /(?<![\d/.\-])\d{1,2}\s*[-/.]\s*\d{1,2}(?![\d/.\-])/g },
    { name: 'week', re: /(?:下|本|这)?周[一二三四五六日天]/g },
    { name: 'days', re: /\d{1,3}\s*天(?:后|之后|以后|内|以内)/g },
    { name: 'month', re: /(?:本|下)?月(?:底|初|中)|年底|年初/g }
  ];

  var DEPARTMENTS = [
    ['研发', '内部'], ['开发', '内部'], ['采购', '内部'], ['品质', '内部'],
    ['生产', '内部'], ['计划', '内部'], ['工程', '内部'], ['模具', '内部'],
    ['财务', '内部'], ['物流', '内部'], ['仓库', '内部'], ['报关', '内部'],
    ['船务', '内部'], ['业务', '内部'], ['客户', '外部'], ['供应商', '外部'],
    ['货代', '外部'], ['第三方', '外部']
  ];

  var EXTERNAL_HINT = /客户\s*(那边|方|的|采购|技术|品质|工程|质量)|供应商|货代|第三方|外部|对方/;

  var NEXT_TRIGGERS = ['下一步', '接下来', '然后', '后面', '回头', '得去', '准备',
    '安排', '需要', '我要', '还得', '明天', '下周'];
  var TIME_TRIGGERS = ['明天', '后天', '下周', '本周', '这周', '月底', '下月初'];
  var BLOCK_TRIGGERS = ['卡在', '卡住', '卡了', '堵在', '等客户', '等供应', '等确认',
    '延迟', '延到', '延期', '要改', '问题', '风险', '还没', '缺', '不过', '但是', '催'];
  var MEANS_TRIGGERS = ['找', '要了', '拿到', '问了', '取了', '调了', '发给', '给了'];
  var DDL_WORDS = ['ddl', 'deadline', '截止', '最晚', '之前要', '必须交', '要交',
    '出货', '交货', '上线', '开模', '打样', '报价'];
  var DDL_LABELS = [['出货', '出货 DDL'], ['交货', '交货 DDL'], ['报价', '报价 DDL'],
    ['打样', '打样 DDL'], ['开模', '开模 DDL'], ['上线', '上线 DDL'],
    ['截止', '截止日'], ['最晚', '最晚期限']];

  function pad(value) { return value < 10 ? '0' + value : String(value); }
  function iso(dateObj) {
    return dateObj.getFullYear() + '-' + pad(dateObj.getMonth() + 1) + '-' + pad(dateObj.getDate());
  }
  function lastDay(year, month) {
    return new Date(year, month, 0).getDate();
  }
  function safeDate(year, month, day) {
    if (month < 1 || month > 12 || day < 1 || day > lastDay(year, month)) return null;
    return new Date(year, month - 1, day);
  }
  function inferYear(month, day, today) {
    var candidate = safeDate(today.getFullYear(), month, day);
    if (!candidate) return today;
    var sixMonthsAgo = new Date(today.getTime() - 180 * 86400000);
    if (candidate < sixMonthsAgo) {
      var next = safeDate(today.getFullYear() + 1, month, day);
      if (next) return next;
    }
    return candidate;
  }

  function collectDates(text, today) {
    var taken = [];
    var found = [];

    function overlaps(start, end) {
      return taken.some(function (span) { return start < span[1] && end > span[0]; });
    }

    PATTERNS.forEach(function (pattern) {
      var re = new RegExp(pattern.re.source, 'g');
      var match;
      while ((match = re.exec(text)) !== null) {
        var raw = match[0];
        if (!raw) { re.lastIndex += 1; continue; }
        var start = match.index;
        var end = start + raw.length;
        if (overlaps(start, end)) continue;
        var value = resolve(raw, pattern.name, today);
        if (!value) continue;
        taken.push([start, end]);
        found.push({
          iso: iso(value), raw: raw.trim(), start: start, end: end,
          inferred: pattern.name !== 'abs'
        });
      }
    });

    found.sort(function (a, b) { return a.start - b.start; });
    return found;
  }

  function resolve(raw, kind, today) {
    var digits = raw.match(/\d+/g) || [];
    if (kind === 'abs' && digits.length >= 3) {
      return safeDate(+digits[0], +digits[1], +digits[2]);
    }
    if (kind === 'cn' && digits.length >= 2) {
      return inferYear(+digits[0], +digits[1], today);
    }
    if (kind === 'cnmonth' && digits.length) {
      var month = +digits[0];
      var day = raw.indexOf('初') >= 0 ? 1 : (raw.indexOf('底') >= 0 ? lastDay(today.getFullYear(), month) : 15);
      var value = safeDate(today.getFullYear(), month, day);
      if (value && value < new Date(today.getTime() - 180 * 86400000)) {
        value = safeDate(today.getFullYear() + 1, month, day);
      }
      return value;
    }
    if (kind === 'md' && digits.length >= 2 && raw.indexOf(':') < 0) {
      return inferYear(+digits[0], +digits[1], today);
    }
    if (kind === 'week') {
      var weekday = WEEKDAY[raw.charAt(raw.length - 1)];
      if (weekday === undefined) return null;
      var monday = new Date(today.getTime() - today.getDay() * 86400000);
      var target = new Date(monday.getTime() + weekday * 86400000);
      if (raw.indexOf('下') === 0) target = new Date(target.getTime() + 7 * 86400000);
      else if (raw.indexOf('本') !== 0 && raw.indexOf('这') !== 0 && target < today) {
        target = new Date(target.getTime() + 7 * 86400000);
      }
      return target;
    }
    if (kind === 'days') {
      return digits.length ? new Date(today.getTime() + (+digits[0]) * 86400000) : null;
    }
    if (kind === 'month') {
      if (raw.indexOf('年底') === 0) return new Date(today.getFullYear(), 11, 31);
      if (raw.indexOf('年初') === 0) return new Date(today.getFullYear(), 0, 1);
      if (raw.indexOf('下月') === 0) {
        var year = today.getFullYear() + (today.getMonth() === 11 ? 1 : 0);
        var nextMonth = today.getMonth() === 11 ? 0 : today.getMonth() + 1;
        return new Date(year, nextMonth, raw.indexOf('初') >= 0 ? 1 : lastDay(year, nextMonth + 1));
      }
      return new Date(today.getFullYear(), today.getMonth(),
        raw.indexOf('初') >= 0 ? 1 : lastDay(today.getFullYear(), today.getMonth() + 1));
    }
    return null;
  }

  function findRange(text, dates) {
    if (!dates.length) return { start: null, end: null };
    for (var i = 0; i < dates.length - 1; i += 1) {
      var left = dates[i], right = dates[i + 1];
      var gap = text.slice(left.end, right.start);
      if (gap.length <= 6 && /^\s*(?:到|至|~|—|–|-)\s*$/.test(gap)) {
        return { start: left, end: right };
      }
    }
    if (dates.length === 1) {
      var only = dates[0];
      var before = text.slice(Math.max(0, only.start - 8), only.start);
      var after = text.slice(only.end, only.end + 4);
      if (/(到|至|截止|最晚|前|DDL|deadline)/i.test(before)) return { start: null, end: only };
      if (/^\s*(前|之前|以前|为止|截止)/.test(after)) return { start: null, end: only };
      if (/(出货|交货|交期|上线|投产|完成|发运)/.test(text.slice(only.end, only.end + 20))) {
        return { start: null, end: only };
      }
      return { start: only, end: null };
    }
    return { start: dates[0], end: dates[dates.length - 1] };
  }

  function findMilestones(text, dates, usedPositions) {
    var out = [];
    var seen = {};
    dates.forEach(function (item) {
      if (usedPositions.indexOf(item.start) >= 0 || seen[item.iso]) return;
      var window_ = text.slice(Math.max(0, item.start - 12), Math.min(text.length, item.end + 16)).toLowerCase();
      var hit = DDL_WORDS.some(function (word) { return window_.indexOf(word) >= 0; });
      if (!hit) return;
      var label = '关键时间点';
      for (var i = 0; i < DDL_LABELS.length; i += 1) {
        if (window_.indexOf(DDL_LABELS[i][0]) >= 0) { label = DDL_LABELS[i][1]; break; }
      }
      seen[item.iso] = true;
      out.push({ date: item.iso, label: label, confidence: item.inferred ? 0.82 : 0.9,
        evidence: text.slice(item.start, Math.min(text.length, item.end + 14)).replace(/^[ ，,、]+|[ ，,、]+$/g, '') });
    });
    return out;
  }

  function normalise(value) {
    return String(value || '').replace(/\s+/g, '').toLowerCase()
      .replace(/(有限公司|股份有限公司|集团|公司|工厂|厂)$/, '');
  }

  function matchCustomer(text, customers) {
    var best = null;
    var haystack = normalise(text);
    (customers || []).forEach(function (customer) {
      var names = [customer.name || ''].concat(String(customer.alias || '').split(',').map(function (x) { return x.trim(); }));
      names.forEach(function (name) {
        if (!name) return;
        var exact = text.indexOf(name) >= 0;
        var fuzzy = normalise(name) && haystack.indexOf(normalise(name)) >= 0;
        if (!exact && !fuzzy) return;
        var score = exact ? 0.95 : 0.82;
        if (!best || score > best.confidence) {
          best = { id: customer.id, name: customer.name, confidence: score, evidence: name };
        }
      });
    });
    return best;
  }

  function matchPhase(text, phases) {
    var ordered = (phases || []).slice().sort(function (a, b) {
      return (b.name || '').length - (a.name || '').length;
    });
    var taken = [];
    var hits = [];
    ordered.forEach(function (phase) {
      var name = phase.name;
      if (!name) return;
      var index = 0;
      while (true) {
        var found = text.indexOf(name, index);
        if (found < 0) break;
        var span = [found, found + name.length];
        var clash = taken.some(function (t) { return span[0] < t[1] && span[1] > t[0]; });
        if (!clash) { taken.push(span); hits.push({ name: name, position: found }); }
        index = found + 1;
      }
    });
    if (!hits.length) return null;
    hits.sort(function (a, b) { return a.position - b.position; });
    return hits[hits.length - 1];
  }

  function findDepartment(text) {
    for (var i = 0; i < DEPARTMENTS.length; i += 1) {
      var word = DEPARTMENTS[i][0];
      var kind = DEPARTMENTS[i][1];
      var index = text.indexOf(word);
      while (index >= 0) {
        var end = index + word.length;
        var suffix = '';
        ['部门', '部', '科', '组'].some(function (item) {
          if (text.slice(end, end + item.length) === item) { end += item.length; suffix = item; return true; }
          return false;
        });
        if (word === '客户' && !suffix) { index = text.indexOf(word, index + 1); continue; }
        return { value: text.slice(index, end), deptType: kind,
          confidence: kind === '内部' ? 0.72 : 0.8, evidence: text.slice(index, end) };
      }
    }
    return null;
  }

  function findContact(text) {
    var match = /(?:找|催|问|联系|让|跟(?!进)|和|叫|对接人)\s*([\u4e00-\u9fa5]{1,4})/.exec(text);
    if (match) {
      var value = match[1];
      DEPARTMENTS.some(function (item) {
        if (value.indexOf(item[0]) === 0 && value.length > item[0].length) {
          value = value.slice(item[0].length);
          return true;
        }
        return false;
      });
      // "催老李确认图纸" grabs "老李确认"; keep the name only. If the match
      // starts with the verb ("跟客户确认"), there is no name to keep.
      var cut = /确认|说|给|发|看|做|要|问|回|把|的|帮|安排/.exec(value);
      if (cut) {
        if (cut.index === 0) return null;
        if (cut.index >= 2) value = value.slice(0, cut.index);
      }
      if (['客户', '他', '她', '那边', '对方'].indexOf(value) >= 0) return null;
      return { value: value, confidence: 0.72, evidence: match[0].trim() };
    }
    var titled = /([\u4e00-\u9fa5]{1,3})(经理|主管|总监|工程师|老师|姐|哥|总)/.exec(text);
    if (titled && titled[0].length >= 2) {
      return { value: titled[0], confidence: 0.75, evidence: titled[0] };
    }
    return null;
  }

  function segments(text) {
    return text.split(/[。！？\n;；，,]+/).map(function (part) {
      return part.replace(/^[ ，,、]+|[ ，,、]+$/g, '');
    }).filter(Boolean);
  }

  function pick(text, triggers, exclude) {
    var picked = [];
    var evidence = '';
    segments(text).forEach(function (segment) {
      if ((exclude || []).some(function (word) { return segment.indexOf(word) >= 0; })) return;
      var hits = triggers.filter(function (word) { return segment.indexOf(word) >= 0; });
      if (!hits.length) return;
      var value = segment;
      var position = Math.min.apply(null, hits.map(function (word) { return segment.indexOf(word); }));
      if (position > 0 && segment.length > 8) value = segment.slice(position);
      picked.push(value);
      if (!evidence) evidence = segment;
    });
    if (!picked.length) return null;
    return { value: picked.join('，').slice(0, 120), confidence: 0.85, evidence: evidence };
  }

  function clean(segment, triggers) {
    var value = segment.replace(/^[ ，,、]+|[ ，,、]+$/g, '');
    for (var i = 0; i < triggers.length; i += 1) {
      var trigger = triggers[i];
      if (value.indexOf(trigger) !== 0) continue;
      if (TIME_TRIGGERS.indexOf(trigger) >= 0) return value.slice(0, 80);
      var rest = value.slice(trigger.length).replace(/^[ ，,、:：]+/, '');
      if ('前后天底初中末个'.indexOf(rest.charAt(0)) >= 0) return value.slice(0, 80);
      return rest.slice(0, 80);
    }
    return value.slice(0, 80);
  }

  function findNext(text) {
    var parts = segments(text);
    for (var i = 0; i < parts.length; i += 1) {
      if (!NEXT_TRIGGERS.some(function (word) { return parts[i].indexOf(word) >= 0; })) continue;
      var value = clean(parts[i], NEXT_TRIGGERS);
      if (value.length < 3 && i + 1 < parts.length) value = parts[i + 1];
      if (value.length >= 2) return { value: value, confidence: 0.86, evidence: parts[i] };
    }
    return null;
  }

  function findName(text, customer) {
    var match = /([\u4e00-\u9fa5A-Za-z0-9][\u4e00-\u9fa5A-Za-z0-9\-]{1,14})\s*(项目|订单|案子|机型)/.exec(text);
    if (!match) return null;
    var base = match[1].trim();
    var names = [];
    if (customer) {
      names.push(customer.name || '');
      names = names.concat(String(customer.alias || '').split(','));
    }
    names.filter(Boolean).sort(function (a, b) { return b.length - a.length; }).forEach(function (name) {
      if (base.indexOf(name) === 0) base = base.slice(name.length).trim();
    });
    base = base.replace(/^(那个|这个|该|其)/, '').replace(/(那个|这个|该)$/, '').trim();
    if (base.indexOf('的') >= 0) base = base.split('的').pop().trim();
    base = base.replace(/^[的了是在和与]/, '').trim();
    if (base.length < 2) return null;
    if (names.some(function (name) { return name && normalise(base) === normalise(name); })) return null;
    return { value: base + '项目', confidence: 0.88, evidence: match[0] };
  }

  function parse(text, customers, phases, today) {
    var now = today || new Date();
    text = String(text || '').trim();
    var fields = {};
    var warnings = [];

    function put(key, value, confidence, evidence) {
      fields[key] = { value: value || '', confidence: Math.round((confidence || 0) * 100) / 100, evidence: evidence || '' };
    }

    if (!text) {
      FIELDS.forEach(function (key) { put(key, '', 0, ''); });
      return { parser: '本地规则', text: '', fields: fields, milestones: [],
        done_phases: [], unresolved: FIELDS.slice(), warnings: ['没有可解析的内容'] };
    }

    var dates = collectDates(text, now);
    var range = findRange(text, dates);
    var used = range.start ? [range.start.start] : [];
    var milestones = findMilestones(text, dates, used);

    var customer = matchCustomer(text, customers);
    var phase = matchPhase(text, phases);
    var department = findDepartment(text);
    var contact = findContact(text);
    var nextAction = findNext(text);
    var blocker = pick(text, BLOCK_TRIGGERS, NEXT_TRIGGERS);
    var means = pick(text, MEANS_TRIGGERS, NEXT_TRIGGERS.concat(['卡']));
    var name = findName(text, customer);

    put('name', name ? name.value : '', name ? name.confidence : 0, name ? name.evidence : '');
    if (customer) {
      fields.customer = { value: customer.id, confidence: customer.confidence,
        evidence: customer.evidence, is_new: false, suggest_name: customer.name };
    } else {
      put('customer', '', 0, '');
    }
    put('phase', phase ? phase.name : '', phase ? 0.95 : 0, phase ? phase.name : '');
    put('start', range.start ? range.start.iso : '', range.start ? (range.start.inferred ? 0.75 : 0.92) : 0, range.start ? range.start.raw : '');
    put('end', range.end ? range.end.iso : '', range.end ? (range.end.inferred ? 0.75 : 0.92) : 0, range.end ? range.end.raw : '');
    if (range.start && range.start.inferred) warnings.push('「' + range.start.raw + '」没写年份，已按最近日期推断');
    if (range.end && range.end.inferred) warnings.push('「' + range.end.raw + '」没写年份，已按最近日期推断');
    if (range.start && range.end && range.end.iso < range.start.iso) warnings.push('结束日期早于开始日期，请核对');

    put('contact', contact ? contact.value : '', contact ? contact.confidence : 0, contact ? contact.evidence : '');
    put('dept', department ? department.value : '', department ? department.confidence : 0, department ? department.evidence : '');
    var deptType = department ? department.deptType : '';
    if (deptType === '内部' && EXTERNAL_HINT.test(text)) deptType = '外部';
    put('deptType', deptType, department ? department.confidence : 0, department ? department.evidence : '');
    put('contactWay', '', 0, '');
    put('means', means ? means.value : '', means ? means.confidence : 0, means ? means.evidence : '');
    put('channel', '', 0, '');
    put('note', blocker ? blocker.value : '', blocker ? blocker.confidence : 0, blocker ? blocker.evidence : '');
    put('next', nextAction ? nextAction.value : '', nextAction ? nextAction.confidence : 0, nextAction ? nextAction.evidence : '');
    put('updated', iso(now), 1, '');

    var unresolved = FIELDS.filter(function (key) {
      return (fields[key] || {}).confidence < 0.7;
    });

    var done = [];
    if (phase) {
      var ordered = (phases || []).slice().sort(function (a, b) { return (a.ordinal || 0) - (b.ordinal || 0); });
      for (var i = 0; i < ordered.length; i += 1) {
        if (ordered[i].name === phase.name) break;
        done.push(ordered[i].name);
      }
    }

    return { parser: '本地规则', text: text, fields: fields, milestones: milestones,
      done_phases: done, unresolved: unresolved, warnings: warnings };
  }

  window.LocalParse = { parse: parse };
})(window);
