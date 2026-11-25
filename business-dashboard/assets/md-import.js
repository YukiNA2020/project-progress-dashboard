/* Markdown 导入解析器。
 *
 * 公司那套 AI 能读云邮件和云群聊，但不能出网写库。所以它负责把原文导成
 * Markdown，这里负责把 Markdown 拆成一条条"候选事实"，再由人勾选合并。
 *
 * 三条设计原则：
 *   1. 按标题切块，逐块解析。把几千字整篇丢给抽取器会丢信息。
 *   2. 每条事实都留原文片段和行号，人能点回去核对。
 *   3. 按正文内容哈希去重，同一份文件导入两次不会产生重复记录。
 *
 * 纯浏览器端，不依赖后端：离线模式也能用。
 */
(function (window) {
  'use strict';

  var META_KEYS = {
    '时间': 'date', '日期': 'date', 'date': 'date',
    '客户': 'customer', '客户名': 'customer', 'customer': 'customer',
    '型号': 'model', '机型': 'model', 'model': 'model',
    '来源': 'source', '渠道': 'source', 'source': 'source',
    '发件人': 'from', 'from': 'from', '对接人': 'from',
    '主题': 'subject', 'subject': 'subject',
    '项目': 'project', 'project': 'project',
    '订单': 'order', 'order': 'order',
    '阶段': 'phase', 'phase': 'phase'
  };

  var SOURCES = ['邮件', '群聊', '微信', '会议', '电话', '口述', '系统'];

  function norm(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }

  /* djb2：够用、够快，不需要加密强度。 */
  function hash(text) {
    var value = 5381;
    var source = norm(text).toLowerCase();
    for (var i = 0; i < source.length; i++) {
      value = ((value << 5) + value + source.charCodeAt(i)) & 0x7fffffff;
    }
    return value.toString(36) + source.length.toString(36);
  }

  function stripMarkup(line) {
    return line
      .replace(/^\s*>\s?/, '')
      .replace(/^\s*[-*+]\s+/, '')
      .replace(/\*\*/g, '')
      .replace(/^["“]|["”]$/g, '');
  }

  /* "- 客户：客户A" / "**时间**: 2026-11-20" / "时间: 2026-11-20" */
  function readMeta(line) {
    var text = stripMarkup(line);
    var match = text.match(/^([\u4e00-\u9fa5A-Za-z ]{1,8})\s*[:：]\s*(.+)$/);
    if (!match) return null;
    var key = META_KEYS[match[1].trim().toLowerCase()] || META_KEYS[match[1].trim()];
    if (!key) return null;
    return { key: key, value: match[2].trim() };
  }

  function splitBlocks(text) {
    var lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
    var blocks = [];
    var current = null;
    var preamble = [];

    function push() {
      if (current && (current.body.join('').trim() || current.heading)) blocks.push(current);
      current = null;
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var heading = line.match(/^(#{1,3})\s+(.+?)\s*$/);
      // 一级标题当文件标题，二三级标题各自起一块。
      if (heading && heading[1].length >= 2) {
        push();
        current = { heading: heading[2], line: i + 1, metaLines: [], body: [] };
        continue;
      }
      if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { push(); continue; }
      if (!current) { preamble.push(line); continue; }
      var meta = readMeta(line);
      if (meta && current.body.length === 0) {
        current.metaLines.push(meta);
      } else {
        current.body.push(line);
      }
    }
    push();

    // 完全没有标题的纯文本：按空行切成不超过约 1200 字的段。
    if (!blocks.length) {
      var chunks = [];
      var buffer = [];
      var size = 0;
      for (var j = 0; j < lines.length; j++) {
        buffer.push(lines[j]);
        size += lines[j].length;
        if ((!lines[j].trim() && size > 600) || size > 1200) {
          if (buffer.join('').trim()) chunks.push(buffer);
          buffer = [];
          size = 0;
        }
      }
      if (buffer.join('').trim()) chunks.push(buffer);
      blocks = chunks.map(function (chunk) {
        return { heading: '', line: 0, metaLines: [], body: chunk };
      });
    }
    return blocks;
  }

  function pickDate(block, bodyText) {
    var meta = findMeta(block, 'date');
    if (meta) {
      var iso = toIso(meta);
      if (iso) return iso;
    }
    var iso2 = toIso(block.heading);
    if (iso2) return iso2;
    return toIso(bodyText);
  }

  function toIso(text) {
    if (!text) return '';
    var full = String(text).match(/(20\d{2})\s*[-\/.年]\s*(\d{1,2})\s*[-\/.月]\s*(\d{1,2})/);
    if (full) {
      return full[1] + '-' + pad(full[2]) + '-' + pad(full[3]);
    }
    var short = String(text).match(/(\d{1,2})\s*[-\/.月]\s*(\d{1,2})(?!\d)/);
    if (short) {
      var year = new Date().getFullYear();
      var month = parseInt(short[1], 10);
      // 12 月看到 1/5 多半是明年，但宁可按今年算，让人在界面上改。
      if (month > 12) return '';
      return year + '-' + pad(short[1]) + '-' + pad(short[2]);
    }
    return '';
  }

  function pad(value) {
    return String(parseInt(value, 10)).padStart(2, '0');
  }

  function findMeta(block, key) {
    for (var i = 0; i < block.metaLines.length; i++) {
      if (block.metaLines[i].key === key) return block.metaLines[i].value;
    }
    return '';
  }

  function detectSource(block, bodyText) {
    var meta = findMeta(block, 'source');
    if (meta) {
      for (var i = 0; i < SOURCES.length; i++) {
        if (meta.indexOf(SOURCES[i]) >= 0) return SOURCES[i];
      }
      return meta;
    }
    var scope = block.heading + ' ' + bodyText;
    for (var j = 0; j < SOURCES.length; j++) {
      if (scope.indexOf(SOURCES[j]) >= 0) return SOURCES[j];
    }
    return '';
  }

  /* 型号是个强特征：字母数字混排、长度 2-12，而且至少含一个数字。 */
  function findModel(text, hint) {
    if (hint) return hint;
    var match = String(text || '').match(/\b([A-Za-z]{1,4}[-]?\d{2,5}[A-Za-z]{0,3})\b/);
    return match ? match[1].toUpperCase() : '';
  }

  /* ---------------------------------------------------------------------
   * 时间点抽取
   *
   * 通用抽取器只把「出货 / 报价 / DDL」当截止线索，可邮件里更常见的写法是
   * 「12/17 前完成生产」「1/15 发货」「1 月底下单」。导入一份邮件如果漏掉
   * 日期，这个功能就失去意义，所以这里单独用一套更宽的线索词。
   * ------------------------------------------------------------------- */

  var DATE_CUES = [
    ['生产完成', '生产完成'], ['完成生产', '生产完成'], ['排产', '排产'],
    ['发货', '发货'], ['装船', '装船'], ['交货', '交货'], ['出货', '出货'],
    ['抽检', '抽检'], ['下单', '下单'], ['订单', '下单'], ['报价', '报价'], ['立项', '立项'],
    ['提交', '提交截止'], ['签章', '签字截止'], ['签字', '签字截止'],
    ['最晚', '最晚期限'], ['截止', '截止日'], ['到期', '到期日']
  ];

  var DATE_PATTERNS = [
    { kind: 'abs', re: /20\d{2}\s*[-\/.年]\s*\d{1,2}\s*[-\/.月]\s*\d{1,2}\s*[日号]?/g },
    { kind: 'cn', re: /\d{1,2}\s*月\s*\d{1,2}\s*[日号]/g },
    { kind: 'md', re: /(?<![\d/.\-])\d{1,2}\s*[-/.]\s*\d{1,2}(?![\d/.\-])/g },
    { kind: 'month', re: /(?:\d{1,2}\s*)?月\s*(?:底|初|中)|年底|年初/g },
    { kind: 'week', re: /(?:下|本|这)?周[一二三四五六日天]/g },
    { kind: 'rel', re: /大后天|今天|明天|后天/g },
    { kind: 'days', re: /\d{1,3}\s*天(?:后|之后|以后|内|以内)/g }
  ];

  function dateToIso(token, kind, anchorIso) {
    var anchor = anchorIso ? new Date(anchorIso + 'T00:00:00') : new Date();
    var year = anchor.getFullYear();
    var match;

    if (kind === 'abs') {
      match = token.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
      if (match) return match[1] + '-' + pad(match[2]) + '-' + pad(match[3]);
      return '';
    }
    if (kind === 'cn' || kind === 'md') {
      match = token.match(/(\d{1,2})\D+(\d{1,2})/);
      if (!match) return '';
      var month = parseInt(match[1], 10);
      var day = parseInt(match[2], 10);
      if (month < 1 || month > 12 || day < 1 || day > 31) return '';
      // 跨年：日期已经过去半年以上，按明年算。
      var guess = new Date(year, month - 1, day);
      if (guess.getTime() < anchor.getTime() - 180 * 86400000) {
        guess = new Date(year + 1, month - 1, day);
      }
      return isoOf(guess);
    }
    if (kind === 'month') {
      match = token.match(/(\d{1,2})\s*月/);
      var mm = match ? parseInt(match[1], 10) : (token.indexOf('下') === 0 ? anchor.getMonth() + 2 : anchor.getMonth() + 1);
      var isLast = token.indexOf('底') >= 0;
      var isMid = token.indexOf('中') >= 0;
      var dd = isLast ? new Date(year, mm, 0).getDate() : (isMid ? 15 : 1);
      var when = new Date(year, mm - 1, dd);
      if (when.getTime() < anchor.getTime() - 180 * 86400000) {
        when = new Date(year + 1, mm - 1, dd);
      }
      return isoOf(when);
    }
    if (kind === 'week') {
      var names = { '一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6 };
      var target = names[token.slice(-1)];
      if (target === undefined) return '';
      var offset = (target - ((anchor.getDay() + 6) % 7) + 7) % 7;
      if (token.indexOf('下') === 0) offset += 7;
      return isoOf(new Date(anchor.getTime() + offset * 86400000));
    }
    if (kind === 'rel') {
      var offsetDays = { '今天': 0, '明天': 1, '后天': 2, '大后天': 3 }[token];
      if (offsetDays === undefined) return '';
      return isoOf(new Date(anchor.getTime() + offsetDays * 86400000));
    }
    if (kind === 'days') {
      match = token.match(/(\d{1,3})/);
      if (!match) return '';
      return isoOf(new Date(anchor.getTime() + parseInt(match[1], 10) * 86400000));
    }
    return '';
  }

  function isoOf(date) {
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
  }

  /* 取离日期最近的那个线索词，只在同一句里找。
   *
   * 「12/17 前完成生产，1/15 发货」里，1/15 到「完成生产」和到「发货」一样远，
   * 只看距离会随机挑一个；日期后面那个词才是它的意思，所以距离相同时取后者。
   * 限定在同一句内，是为了避免把上一句的「发货」安到下一句的「今天」头上。 */
  function closestCue(window_, dateOffset) {
    var best = '';
    var bestDistance = 1e9;
    var bestPos = -1;
    for (var i = 0; i < DATE_CUES.length; i++) {
      var word = DATE_CUES[i][0];
      var pos = window_.indexOf(word);
      while (pos >= 0) {
        var distance = Math.abs(pos - dateOffset);
        var after = pos > dateOffset;
        var better = distance < bestDistance ||
          (distance === bestDistance && after && bestPos <= dateOffset);
        if (better) {
          bestDistance = distance;
          best = DATE_CUES[i][1];
          bestPos = pos;
        }
        pos = window_.indexOf(word, pos + 1);
      }
    }
    return best;
  }

  function sentenceAround(text, start, end) {
    var cut = -1;
    var boundary = '。；;！!\n';
    for (var i = start - 1; i >= 0; i--) {
      if (boundary.indexOf(text.charAt(i)) >= 0) { cut = i + 1; break; }
    }
    var from = cut < 0 ? Math.max(0, start - 40) : cut;
    var to = text.length;
    for (var j = end; j < text.length; j++) {
      if (boundary.indexOf(text.charAt(j)) >= 0) { to = j; break; }
    }
    return { from: from, to: Math.min(to, from + 120) };
  }

  function extractMilestones(text, anchorIso, heading) {
    var found = [];
    var taken = {};
    DATE_PATTERNS.forEach(function (pattern) {
      pattern.re.lastIndex = 0;
      var match;
      while ((match = pattern.re.exec(text)) !== null) {
        var token = match[0];
        var start = match.index;
        var iso = dateToIso(token, pattern.kind, anchorIso);
        if (!iso || taken[iso]) continue;
        var span = sentenceAround(text, start, start + token.length);
        var window_ = text.slice(span.from, span.to);
        var label = closestCue(window_, start - span.from);
        // 「第二笔订单 1 月底下」这种句子本身没有线索词，就看标题在说什么。
        if (!label && heading) {
          for (var h = 0; h < DATE_CUES.length; h++) {
            if (heading.indexOf(DATE_CUES[h][0]) >= 0) { label = DATE_CUES[h][1]; break; }
          }
        }
        if (!label) continue;
        taken[iso] = true;
        found.push({
          date: iso,
          label: label,
          evidence: text.slice(Math.max(0, start - 8), Math.min(text.length, start + token.length + 12))
        });
      }
    });
    return found.sort(function (a, b) { return a.date.localeCompare(b.date); });
  }

  function resolveCustomer(name, customers) {
    if (!name) return { id: '', name: '' };
    var target = norm(name).toLowerCase();
    for (var i = 0; i < customers.length; i++) {
      var customer = customers[i];
      var candidates = [customer.name].concat(String(customer.alias || '').split(/[,，;；\s]+/));
      for (var j = 0; j < candidates.length; j++) {
        var value = norm(candidates[j]).toLowerCase();
        if (!value) continue;
        if (value === target || target.indexOf(value) >= 0 || value.indexOf(target) >= 0) {
          return { id: customer.id, name: customer.name };
        }
      }
    }
    return { id: '', name: norm(name) };
  }

  /* 先按型号精确匹配，再退回客户名 + 型号出现在正文里。 */
  function matchProject(candidate, projects, customers) {
    var model = (candidate.model || '').toUpperCase();
    if (model) {
      for (var i = 0; i < projects.length; i++) {
        var project = projects[i];
        var own = String(project.model || '').toUpperCase();
        if (own && own === model) return project.id;
        if (!own && String(project.name || '').toUpperCase().indexOf(model) >= 0) {
          return project.id;
        }
      }
    }
    if (candidate.customerId) {
      var same = projects.filter(function (project) {
        return project.customer === candidate.customerId;
      });
      if (same.length === 1) return same[0].id;
    }
    return '';
  }

  var MD = {};

  MD.hash = hash;

  MD.parse = function (text, customers, projects, phases) {
    customers = customers || [];
    projects = projects || [];
    phases = phases || [];

    var blocks = splitBlocks(text);
    var rows = [];
    var seen = {};

    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      var bodyText = block.body.join('\n').replace(/^\s*>\s?/gm, '');
      var plain = norm(bodyText);
      if (!plain && !block.heading) continue;

      var key = hash(block.heading + '\u0000' + plain);
      var duplicateInFile = !!seen[key];
      seen[key] = true;

      var parser = window.LocalParse;
      var parsed = null;
      try {
        parsed = parser ? parser.parse(plain, customers, phases) : null;
      } catch (error) {
        parsed = null;
      }
      var fields = (parsed && parsed.fields) || {};
      var value = function (name) {
        return fields[name] && fields[name].value ? fields[name].value : '';
      };
      var evidence = function (name) {
        return fields[name] && fields[name].evidence ? fields[name].evidence : '';
      };

      var declaredCustomer = findMeta(block, 'customer');
      var resolved = resolveCustomer(declaredCustomer, customers);
      if (!resolved.id) {
        var guessed = value('customer');
        if (guessed) {
          var alt = resolveCustomer(guessed, customers);
          if (alt.id) resolved = alt;
        }
      }

      var blockDate = pickDate(block, plain);
      var milestones = extractMilestones(plain, blockDate, block.heading);
      if (!milestones.length && parsed && parsed.milestones) milestones = parsed.milestones;

      // 「和第一单撞」会被通用抽取器当成联系人，这类词一律丢掉。
      var guessedFrom = value('contact');
      if (guessedFrom && (guessedFrom.length > 4 || /[单撞期货款期船]/.test(guessedFrom))) {
        guessedFrom = '';
      }

      var candidate = {
        key: key,
        index: i + 1,
        heading: norm(block.heading),
        line: block.line,
        date: blockDate,
        source: detectSource(block, plain),
        from: findMeta(block, 'from') || guessedFrom,
        subject: findMeta(block, 'subject'),
        customerId: resolved.id,
        customerName: resolved.name || value('customer') || '未识别',
        customerIsNew: !resolved.id && !!resolved.name,
        model: findModel(block.heading + ' ' + plain, findMeta(block, 'model')),
        phase: findMeta(block, 'phase') || value('phase'),
        note: value('note'),
        next: value('next'),
        start: value('start'),
        end: value('end'),
        milestones: milestones,
        evidence: {
          phase: evidence('phase'),
          note: evidence('note'),
          next: evidence('next'),
          end: evidence('end')
        },
        duplicateInFile: duplicateInFile,
        duplicateInStore: false,
        excerpt: plain.slice(0, 400),
        raw: plain
      };
      candidate.projectId = matchProject(candidate, projects, customers);
      candidate.confidence = score(candidate);
      rows.push(candidate);
    }

    return {
      blocks: rows,
      stats: {
        blocks: rows.length,
        withCustomer: rows.filter(function (r) { return r.customerId; }).length,
        withModel: rows.filter(function (r) { return r.model; }).length,
        matched: rows.filter(function (r) { return r.projectId; }).length
      }
    };
  };

  /* 置信度只用来排序和标黄，不用来决定"要不要人看"——所有条目都要人看。 */
  function score(candidate) {
    var value = 0;
    if (candidate.date) value += 0.25;
    if (candidate.customerId) value += 0.25;
    if (candidate.model) value += 0.2;
    if (candidate.phase) value += 0.15;
    if (candidate.projectId) value += 0.15;
    return Math.round(value * 100) / 100;
  }

  MD.markStored = function (rows, storedHashes) {
    var known = {};
    (storedHashes || []).forEach(function (item) { known[item] = true; });
    rows.forEach(function (row) {
      row.duplicateInStore = !!known[row.key];
    });
    return rows;
  };

  window.MDImport = MD;
})(window);
