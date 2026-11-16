/* Undertow page: renders data/snapshot.json. All text from data goes through esc(). */
(function () {
  "use strict";

  var PUB = { meta: "Meta", google: "Google", openai: "OpenAI", tiktok: "TikTok", eeas: "EEAS", dfrlab: "DFRLab",
    checkfirst: "CheckFirst", correctiv: "CORRECTIV", watch: "Watch register" };
  var ORDER = ["meta", "google", "openai", "tiktok", "eeas", "dfrlab", "checkfirst", "correctiv", "watch"];
  var PAGE = 60;
  var T = window.TicTime;

  function esc(v) {
    return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function when(iso) {
    // House rule: the viewer's own zone by default, the zone always named, changed from the Time menu.
    if (!iso) { return ""; }
    if (T) { try { return T.format(iso, { year: true }); } catch (e) { /* fall through */ } }
    try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZoneName: "short" }); } catch (e) { return iso; }
  }
  function day(iso) { return iso ? String(iso).slice(0, 10) : ""; }
  function stamp(iso, precision) {
    // A publisher date with no time of day is shown as the month or the date, read in UTC, never shifted into the
    // viewer's zone (tic-feed/2 data_as_of_precision).
    if (precision === "month") {
      try { return new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric", timeZone: "UTC" }) + " (month only)"; }
      catch (e) { return String(iso).slice(0, 7) + " (month only)"; }
    }
    return precision === "day" || /T00:00:00(\.0+)?Z$/.test(iso || "") ? day(iso) + " (date only)" : when(iso);
  }
  function num(n) { return Number(n).toLocaleString("en-US"); }
  function link(url, label) { return '<a href="' + esc(url) + '" rel="noopener">' + esc(label) + "</a>"; }

  var S, NAMES, filtered = [], shown = PAGE;
  function cname(c) { return NAMES[c] || c; }
  function places(list) { return (list || []).map(cname).join(", "); }

  function itemDate(it) {
    if (it.publisher === "google" && it.period && /^\d{4}-\d{2}$/.test(it.period)) { return it.period + "-15"; }
    return day(it.disclosed_at) || (it.period && /^\d{4}/.test(it.period) ? String(it.period).slice(0, 4) + "-06-30" : "");
  }

  function tiles(items) {
    var origins = {}, ops = {};
    items.forEach(function (it) {
      (it.origin || []).forEach(function (c) { origins[c] = 1; });
      (it.named_operations || []).forEach(function (o) { (ops[o] = ops[o] || {})[it.publisher] = 1; });
    });
    var multi = Object.keys(ops).filter(function (o) { return Object.keys(ops[o]).length > 1; }).length;
    var withTech = items.filter(function (it) { return (it.disarm || []).length; }).length;
    var act = items.filter(function (it) { return it.activity; });
    document.getElementById("tiles").innerHTML = [
      ["Disclosed networks and operations", num(items.length - act.length)],
      ["Reported activity (active / quiet)", num(act.filter(function (it) { return it.activity.state === "active"; }).length) + " / " +
        num(act.filter(function (it) { return it.activity.state !== "active"; }).length)], ["Publishers", ORDER.filter(function (p) { return items.some(function (i) { return i.publisher === p; }); }).length],
      ["Origin countries stated", Object.keys(origins).length], ["Named operations with 2+ publishers", multi],
      ["With a DISARM technique", num(withTech)]
    ].map(function (t) { return '<div class="tile"><span class="k">' + esc(t[0]) + '</span><span class="v">' + esc(t[1]) + "</span></div>"; }).join("");
  }

  function timeline(items) {
    var groups = {};
    items.forEach(function (it) {
      var d = itemDate(it);
      if (!d) { return; }
      var k = it.publisher + "|" + (it.publisher === "google" ? it.period : it.disclosure.id);
      var g = groups[k] = groups[k] || { pub: it.publisher, date: d, n: 0, title: it.disclosure.title };
      g.n += 1;
    });
    var list = Object.keys(groups).map(function (k) { return groups[k]; });
    if (!list.length) { return; }
    var t0 = Date.parse("2024-01-01"), t1 = Date.now() + 30 * 864e5;
    list.forEach(function (g) { var t = Date.parse(g.date); if (t < t0) { t0 = t; } });
    var W = 1000, L = 76, R = 16, rowH = 44, top = 18, H = top + rowH * ORDER.length + 26;
    function x(t) { return L + (W - L - R) * (t - t0) / (t1 - t0); }
    var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Disclosures by publisher over time">'];
    ORDER.forEach(function (p, i) {
      var y = top + rowH * i + rowH / 2;
      svg.push('<line class="axis" x1="' + L + '" x2="' + (W - R) + '" y1="' + y + '" y2="' + y + '"/>');
      svg.push('<text class="lane-label" x="0" y="' + (y + 4) + '">' + esc(PUB[p]) + "</text>");
    });
    for (var yr = new Date(t0).getUTCFullYear(); yr <= new Date(t1).getUTCFullYear(); yr++) {
      [0, 6].forEach(function (m) {
        var t = Date.UTC(yr, m, 1);
        if (t < t0 || t > t1) { return; }
        var xx = x(t);
        svg.push('<line class="axis" x1="' + xx + '" x2="' + xx + '" y1="' + top + '" y2="' + (H - 22) + '" stroke-dasharray="2 4"/>');
        svg.push('<text x="' + (xx + 3) + '" y="' + (H - 8) + '">' + (m === 0 ? yr : "Jul") + "</text>");
      });
    }
    list.sort(function (a, b) { return b.n - a.n; }).forEach(function (g) {
      var i = ORDER.indexOf(g.pub), y = top + rowH * i + rowH / 2;
      var r = Math.max(3, Math.min(18, 2.2 * Math.sqrt(g.n)));
      svg.push('<circle class="dot dot-' + g.pub + '" cx="' + x(Date.parse(g.date)).toFixed(1) + '" cy="' + y + '" r="' + r.toFixed(1) +
        '"><title>' +
        esc(g.title + ", " + g.date.slice(0, 7) + ": " + g.n + (g.n === 1 ? " network" : " networks")) + "</title></circle>");
    });
    svg.push("</svg>");
    document.getElementById("timeline").innerHTML = svg.join("");
  }

  function matrix(items) {
    var rows = {}, cols = {}, cell = {};
    items.filter(function (it) { return !it.activity; }).forEach(function (it) {
      var o = (it.origin || []).length ? it.origin : ["?"];
      var t = (it.targets || []).length ? it.targets : ["-"];
      o.forEach(function (a) {
        rows[a] = (rows[a] || 0) + 1;
        t.forEach(function (b) { cols[b] = (cols[b] || 0) + 1; cell[a + "|" + b] = (cell[a + "|" + b] || 0) + 1; });
      });
    });
    function top(obj, n) { return Object.keys(obj).filter(function (k) { return k !== "?" && k !== "-"; }).sort(function (a, b) { return obj[b] - obj[a]; }).slice(0, n); }
    var R = top(rows, 14).concat(rows["?"] ? ["?"] : []), C = top(cols, 14).concat(cols["-"] ? ["-"] : []);
    var max = 1;
    R.forEach(function (a) { C.forEach(function (b) { max = Math.max(max, cell[a + "|" + b] || 0); }); });
    function lab(c) { return c === "?" ? "no origin stated" : c === "-" ? "none named" : cname(c); }
    var h = "<thead><tr><th scope=\"col\" class=\"rowh\">Origin \\ target</th>" + C.map(function (c) { return '<th scope="col" title="' + esc(lab(c)) + '">' + esc(c === "-" ? "none" : c === "?" ? "?" : c) + "</th>"; }).join("") + "</tr></thead><tbody>";
    R.forEach(function (a) {
      h += '<tr><th scope="row" class="rowh">' + esc(lab(a)) + "</th>";
      C.forEach(function (b) {
        var n = cell[a + "|" + b] || 0;
        var lvl = n ? Math.min(5, 1 + Math.floor(4.999 * Math.sqrt(n / max))) : 0;   // classes, not inline style (CSP)
        h += '<td class="c c' + lvl + '"' + (n ? ' title="' + esc(lab(a) + " to " + lab(b) + ": " + n) + '"' : "") + ">" + (n || "") + "</td>";
      });
      h += "</tr>";
    });
    document.getElementById("matrix").innerHTML = h + "</tbody>";
  }

  function namedOps(items) {
    var ops = {};
    var names = {};
    (S.operations || []).forEach(function (o) { names[o.id] = o; });
    items.forEach(function (it) {
      (it.named_operations || []).forEach(function (o) {
        var g = ops[o] = ops[o] || { pubs: {}, origins: {}, align: {}, conf: null, n: 0, last: null };
        g.pubs[it.publisher] = 1; g.n += 1;
        if (it.activity && (!g.last || it.activity.last_report > g.last.date)) { g.last = { date: it.activity.last_report, who: PUB[it.publisher] === PUB.watch ? it.reporter : PUB[it.publisher], state: it.activity.state }; }
        (it.origin || []).forEach(function (c) { (g.origins[c] = g.origins[c] || {})[PUB[it.publisher]] = 1; });
        (it.alignment || []).forEach(function (c) { g.align[c] = 1; });
      });
    });
    Object.keys(ops).forEach(function (k) {
      // Per operation: independent publishers stating the same origin. One is Low, two or more Moderate (capped).
      var best = 0;
      Object.keys(ops[k].origins).forEach(function (c) { best = Math.max(best, Object.keys(ops[k].origins[c]).length); });
      var split = Object.keys(ops[k].origins).length > 1;
      ops[k].conf = best === 0 ? null : (best >= 2 ? "moderate" : "low") + (split ? ", origins differ" : "");
    });
    var keys = Object.keys(ops).sort(function (a, b) { return Object.keys(ops[b].pubs).length - Object.keys(ops[a].pubs).length || ops[b].n - ops[a].n; });
    document.getElementById("ops").innerHTML = keys.map(function (k) {
      var g = ops[k], o = names[k] || { name: k, aliases: [] };
      var origin = Object.keys(g.origins).map(function (c) { return cname(c) + " (" + Object.keys(g.origins[c]).join(", ") + ")"; }).join("; ");
      var align = Object.keys(g.align).map(cname).join(", ");
      return '<div class="oprow"><span class="n">' + esc(o.name) + "</span>" +
        (o.aliases && o.aliases.length ? '<span class="small muted">also ' + esc(o.aliases.join(", ")) + "</span>" : "") +
        '<div class="small">' + ORDER.filter(function (p) { return g.pubs[p]; }).map(function (p) { return '<span class="pub pub-' + p + '">' + esc(PUB[p]) + "</span>"; }).join(" · ") +
        " · " + g.n + (g.n === 1 ? " item" : " items") +
        (origin ? " · origin stated: " + esc(origin) : " · no origin stated") + (align ? " · aligned with " + esc(align) + " (EEAS)" : "") +
        (g.conf ? ' · <span class="badge">our confidence in origin: ' + esc(g.conf) + "</span>" : "") +
        (g.last ? " · last reported " + esc(day(g.last.date)) + " by " + esc(g.last.who) + " (" + esc(g.last.state) + ")" : "") + "</div></div>";
    }).join("") || '<p class="small muted">No named operations.</p>';
  }

  function counts(c) {
    var w = { facebook_accounts: "Facebook accounts", instagram_accounts: "Instagram accounts", facebook_pages: "Pages",
      accounts: "accounts", followers: "followers", youtube_channels: "YouTube channels", blogger_blogs: "Blogger blogs",
      ads_accounts: "Ads accounts", play_accounts: "Play accounts", news_discover_domains: "domains blocked from News and Discover",
      indicators: "indicators (count only)", websites: "websites", operations: "operations" };
    return Object.keys(c || {}).filter(function (k) { return typeof c[k] === "number"; }).map(function (k) { return num(c[k]) + " " + (w[k] || k.replace(/_/g, " ")); }).join(", ");
  }

  function activityFacts(it) {
    var a = it.activity, who = it.publisher === "watch" ? it.reporter : PUB[it.publisher];
    var links = (a.report_links || []).slice(0, 12).map(function (x) { return link(x.url, day(x.date)); }).join(", ") +
      ((a.report_links || []).length > 12 ? " and " + ((a.report_links || []).length - 12) + " earlier" : "");
    var where = (it.targets || []).length ? "targets as the reporter states them: " + places(it.targets) :
      (it.countries_named || []).length ? "named in the reports: " + places(it.countries_named) : "none named";
    return [
      ["Reporter", '<span class="pub pub-' + it.publisher + '">' + esc(who) + "</span>" + (it.reporter && it.reporter !== who ? ", " + esc(it.reporter) : "") + " (grade " + esc(a.grade) + "; a reporter, not the platform that acted)"],
      ["Reported activity", '<span class="badge' + (a.state === "active" ? "" : " badge-warn") + '">' + esc(a.state) + "</span> " +
        esc(a.reports + (a.reports === 1 ? " report" : " reports") + ", first " + day(a.first_report) + ", last " + day(a.last_report) +
        "; quiet after " + a.quiet_after_days + " days without a report (never \u201cended\u201d), as of " + a.state_as_of)],
      ["Reports", links],
      ["Countries", esc(where + ((it.target_regions || []).length ? "; " + it.target_regions.join(", ") : ""))],
      ["Platforms", esc((it.platforms || []).join(", "))],
      ["Origin", it.origin.length ? esc(places(it.origin)) + " (" + esc(it.origin_level) + ")" : "not read: Undertow records that " + esc(who) + " reported the operation, not its attribution"],
      ["Our confidence in origin", it.confidence ? esc(it.confidence) : "none (a reporter corroborates that the operation was reported, not its origin)"],
      ["DISARM", (it.disarm || []).map(function (d) { return esc(d.id + " " + d.name) + " (rule " + esc(d.rule) + ")"; }).join("; ") || "no rule matched"]
    ].filter(function (f) { return f[1]; });
  }

  function row(it) {
    var tech = (it.disarm || []).map(function (d) { return '<span class="badge" title="' + esc(d.name + (d.phrase ? ': "' + d.phrase + '"' : "")) + '">' + esc(d.id) + "</span>"; }).join("");
    var target = places(it.targets) + ((it.target_regions || []).length ? (it.targets.length ? "; " : "") + it.target_regions.join(", ") : "");
    var facts = [
      ["Publisher", '<span class="pub pub-' + it.publisher + '">' + esc(PUB[it.publisher]) + "</span>, " + link(it.url, it.disclosure.title) + (it.page ? " (p. " + esc(it.page) + ")" : "")],
      [it.publisher === "meta" ? "Added to Meta's repository" : "Disclosed", esc(it.disclosed_at ? stamp(it.disclosed_at, it.disclosed_precision) : "not dated") + (it.period ? " · period " + esc(it.period) : "")],
      ["Origin (publisher's judgment)", it.publisher === "dfrlab" ? "not read: Undertow records only that DFRLab reported on the operation" : it.origin.length ? esc(places(it.origin)) + (it.origin_wording ? ' · "' + esc(it.origin_wording) + '"' : "") + ' · stated level: ' + esc(it.origin_level) : "none stated" + (it.alignment.length ? "; aligned with " + esc(places(it.alignment)) : "") + (it.origin_wording ? ' · "' + esc(it.origin_wording) + '"' : "")],
      ["Operator named", it.orgs.length ? esc(it.orgs.join(", ")) : "none"],
      ["Targets", target ? esc(target) : (it.countries_named.length ? "none stated; countries named in the description: " + esc(places(it.countries_named)) : "none stated")],
      ["Counts", esc(counts(it.counts)) || "none stated"],
      ["Languages", esc((it.languages || []).join(", "))],
      ["Our confidence in origin", it.confidence ? esc(it.confidence) + (it.corroborated_by.length ? " (also named by " + esc(it.corroborated_by.map(function (p) { return p === "eu-eeas" ? "EEAS" : PUB[p] || p; }).join(", ")) + ")" : " (one publisher)") : it.publisher === "dfrlab" ? "none (corroborates that the operation was reported, not its origin)" : "none (no origin stated)"],
      ["DISARM", (it.disarm || []).map(function (d) { return esc(d.id + " " + d.name) + (d.phrase ? ' (rule ' + esc(d.rule) + ': "' + esc(d.phrase) + '")' : " (rule " + esc(d.rule) + ")"); }).join("; ") || "no rule matched"]
    ].filter(function (f) { return f[1]; });
    if (it.activity) { facts = activityFacts(it); }
    var body = "<p>" + esc(it.summary) + "</p>" +
      (it.publisher_text ? "<blockquote>" + esc(it.publisher_text) + "<br><span class=\"small\">" + esc(it.publisher_text_note) + "</span></blockquote>" : "") +
      ((it.behaviours || []).length ? "<blockquote>" + it.behaviours.map(function (b) { return '"' + esc(b.text) + '" (p. ' + esc(b.page) + ")"; }).join("<br>") + '<br><span class="small">Source: European External Action Service, 4th report on FIMI threats.</span></blockquote>' : "") +
      '<dl class="facts">' + facts.map(function (f) { return "<dt>" + esc(f[0]) + "</dt><dd>" + f[1] + "</dd>"; }).join("") + "</dl>" +
      (it.withheld ? '<p class="small muted">' + it.withheld + " name or link span" + (it.withheld === 1 ? "" : "s") + " withheld from the publisher's text.</p>" : "") +
      '<p class="small muted">Item ' + esc(it.id) + "</p>";
    return '<details class="op" id="' + esc(it.id) + '"><summary><span class="small muted">' + esc(itemDate(it).slice(0, 7)) + '</span><span class="pub pub-' + it.publisher + '">' + esc(PUB[it.publisher]) +
      '</span><span class="t">' + esc(it.title) + ' <span class="small muted">' + esc(it.activity ? it.activity.reports + (it.activity.reports === 1 ? " report" : " reports") : it.origin.length ? "origin " + places(it.origin) : "no origin stated") + "</span> " + tech + "</span></summary><div class=\"body\">" + body + "</div></details>";
  }

  function applyFilter() {
    var pub = document.getElementById("f-pub").value, q = document.getElementById("f-q").value.trim().toLowerCase();
    filtered = S.items.filter(function (it) {
      if (pub && it.publisher !== pub) { return false; }
      if (!q) { return true; }
      var hay = [it.title, it.summary, it.operation_name, places(it.origin), places(it.targets), places(it.countries_named),
        (it.target_regions || []).join(" "), (it.disarm || []).map(function (d) { return d.id + " " + d.name; }).join(" "),
        (it.named_operations || []).join(" ")].join(" ").toLowerCase();
      return hay.indexOf(q) >= 0;
    }).sort(function (a, b) { return itemDate(b) < itemDate(a) ? -1 : itemDate(b) > itemDate(a) ? 1 : 0; });
    shown = PAGE;
    drawRows();
  }
  function drawRows() {
    document.getElementById("rows").innerHTML = filtered.slice(0, shown).map(row).join("") || '<p class="small muted">Nothing matches.</p>';
    document.getElementById("f-count").textContent = Math.min(shown, filtered.length) + " of " + filtered.length + " shown";
    var more = document.getElementById("more");
    more.hidden = filtered.length <= shown;
  }

  function method() {
    var w = S.items.reduce(function (a, it) { return a + (it.withheld || 0); }, 0);
    document.getElementById("withheld-n").textContent = "In this collection " + w + " span" + (w === 1 ? " was" : "s were") + " withheld.";
    document.getElementById("disarm-v").textContent = S.disarm_version;
    document.getElementById("rules-status").textContent = S.disarm_rules_status === "reviewed" ?
      "The rule table is reviewed. A technique is still Undertow's reading of the publisher's words, not the publisher's claim." :
      "The rule table is proposed and not yet reviewed by Tom: read every technique here as provisional.";
    var used = {};
    S.items.forEach(function (it) { (it.disarm || []).forEach(function (d) { used[d.rule] = (used[d.rule] || 0) + 1; }); });
    document.getElementById("rules").innerHTML = "<thead><tr><th scope=\"col\">Rule</th><th scope=\"col\">Technique</th><th scope=\"col\">Reads</th><th scope=\"col\">Items</th></tr></thead><tbody>" +
      S.rules.map(function (r) { return "<tr><td>" + esc(r.id) + "</td><td>" + esc(r.technique) + "</td><td>" + esc(r.about) + "</td><td>" + (used[r.id] || 0) + "</td></tr>"; }).join("") + "</tbody>";
    var labels = { meta: "Meta threat-research repository", google: "Google Influence Operations Bulletin", openai: "OpenAI news RSS",
      tiktok: "TikTok via the EU Code of Conduct Transparency Centre", eeas: "EEAS FIMI report (register) and FIMI page", dfrlab: "DFRLab RSS feed (reported activity)",
      checkfirst: "CheckFirst RSS feed (reported activity)", correctiv: "CORRECTIV English RSS feed (reported activity)",
      watch: "Watch register (hand-kept)" };
    document.getElementById("lanes").innerHTML = ORDER.map(function (k) {
      var l = (S.lanes || {})[k] || {}, ok = l.status === "ok";
      var note = ok ? "collected " + when(l.fetched_at) + ", " + (l.items || 0) + " items" : (l.from_previous && l.fetched_at ? "failed; showing the copy from " + when(l.fetched_at) : "failed; no data");
      var ex = (S.extra || {})[k] || {};
      if (k === "google" && ex.pages) {
        note += ". Bulletins read: " + ex.pages.map(function (p) { return "Q" + p.quarter + " " + p.year + " (" + p.entries + " entries, " + p.unparsed.length + " unparsed)"; }).join(", ") +
          (ex.not_published && ex.not_published.length ? "; not yet published: " + ex.not_published.join(", ") : "");
      }
      if (k === "tiktok" && ex.reports) { note += ". Reports read: " + ex.reports.map(function (r) { return r.name + " (" + r.networks + " networks)"; }).join(", "); }
      if (k === "eeas" && ex.page) { note += ". 4th report still listed: " + (ex.page.listed ? "yes" : "no") + (ex.page.newer_report ? "; a newer report (" + ex.page.newer_report + "th) is listed: its register needs extracting" : "; no newer report listed"); }
      if (k === "watch") { note = ok ? (ex.rows || 0) + " rows, entered by hand after Tom's review" : note; }
      if ((k === "dfrlab" || k === "checkfirst" || k === "correctiv") && ex.items_read) { note += ". " + ex.items_read + " feed items read this run (" + ex.pages_read + (ex.pages_read === 1 ? " page" : " pages") + "); only articles naming a tracked operation are kept"; }
      if (k === "openai" && ex.roundups) { note += ". " + ex.roundups.length + " report round-ups kept as disclosures, not operations"; }
      return '<p class="small"><strong>' + esc(labels[k]) + '</strong> <span class="badge' + (ok ? "" : " badge-warn") + '">' + (ok ? "current" : "not current") + "</span><br>" + esc(note) + "</p>";
    }).join("");
    document.getElementById("events").innerHTML = (S.events || []).map(function (e) { return "<li>" + esc(e.date) + ": " + esc(e.title) + "</li>"; }).join("");
  }

  function render() {
    NAMES = S.country_names || {};
    document.getElementById("asof").textContent = "Collected " + when(S.generated_at) + ". Method " + S.method_version + ", DISARM v" + S.disarm_version + ".";
    tiles(S.items);
    timeline(S.items);
    matrix(S.items);
    namedOps(S.items);
    method();
    drawRows();
  }

  fetch("data/snapshot.json")
    .then(function (r) { return r.json(); })
    .then(function (s) {
      S = s;
      NAMES = S.country_names || {};
      var sel = document.getElementById("f-pub");
      ORDER.forEach(function (p) { var o = document.createElement("option"); o.value = p; o.textContent = PUB[p]; sel.append(o); });
      sel.addEventListener("change", applyFilter);
      document.getElementById("f-q").addEventListener("input", applyFilter);
      document.getElementById("more").addEventListener("click", function () { shown += PAGE; drawRows(); });
      filtered = S.items.slice();
      applyFilter();
      render();
      var h = location.hash.slice(1);
      if (h) {
        var i = filtered.findIndex(function (it) { return it.id === h; });
        if (i >= shown) { shown = i + 1; drawRows(); }
        var el = document.getElementById(h);
        if (el && el.tagName === "DETAILS") { el.open = true; }
        if (el) { el.scrollIntoView(); }
      }
      if (T) {
        var slot = document.getElementById("time-settings");
        if (slot) { T.mountSettings(slot); }
        T.onChange(function () { render(); });
      }
    })
    .catch(function (e) { document.getElementById("asof").textContent = "The data could not be loaded."; if (window.console) { console.error(e); } });
})();
