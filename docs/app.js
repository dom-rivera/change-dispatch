/* The Change Dispatch: front-end.
   Reads data/items.json, data/status.json and data/editions/*.json
   (written daily by scripts/fetch.py) and renders the sections.
   All text from feeds is inserted with textContent, never as HTML. */
(function () {
  "use strict";

  var DAY = 86400000;
  var TZ = "Asia/Manila";
  var TYPES = ["Peer-reviewed", "Preprint", "Institutional", "Expert analysis", "News"];
  var LAYER_NAMES = { research: "Peer-reviewed", preprint: "Preprint", institutional: "Institutional",
                      analysis: "Expert analysis", news: "News" };

  var state = {
    items: [], byId: {}, topics: [], region: null, status: null, generated: null,
    editions: null, editionCache: {}, type: "All", query: ""
  };

  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] === undefined || attrs[k] === null || attrs[k] === "") return;
      if (k === "text") node.textContent = attrs[k];
      else if (k === "class") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function fmtDate(d, withTime) {
    var opts = { timeZone: TZ, year: "numeric", month: "short", day: "numeric" };
    if (withTime) { opts.hour = "numeric"; opts.minute = "2-digit"; }
    return d.toLocaleString("en-US", opts);
  }

  function longDate(isoDay) {
    // isoDay is a Manila calendar date like 2026-11-10
    var d = new Date(isoDay + "T12:00:00+08:00");
    return d.toLocaleDateString("en-US", { timeZone: TZ, weekday: "long", year: "numeric", month: "long", day: "numeric" });
  }

  function ageDays(item) { return (Date.now() - new Date(item.published).getTime()) / DAY; }
  function isCurrent(item) { return ageDays(item) <= item.window_days; }

  function freshness(item) {
    var a = ageDays(item);
    if (a < 1) return { text: "New today", cls: "new" };
    if (a <= 7) return { text: "This week", cls: "" };
    if (a <= 31) return { text: "This month", cls: "" };
    return null;
  }

  function topicName(id) {
    for (var i = 0; i < state.topics.length; i++) if (state.topics[i].id === id) return state.topics[i].name;
    return id;
  }

  function coreIds() {
    return state.topics.filter(function (t) { return t.group === "core"; }).map(function (t) { return t.id; });
  }

  /* ---------------- Sections ---------------- */

  function sectionFor(hash) {
    var h = (hash || "").replace(/^#/, "") || "today";
    if (h === "front") return {
      key: h, title: "Front Page",
      note: "Current items on change readiness, self-efficacy, openness to change, organizational change and change management.",
      filter: function (i) { return isCurrent(i) && i.topics.some(function (t) { return coreIds().indexOf(t) >= 0; }); }
    };
    if (h === "research") return {
      key: h, title: "Research Desk",
      note: "Peer-reviewed papers with a free legal copy, plus preprints and working papers (clearly labeled).",
      filter: function (i) { return isCurrent(i) && (i.layer === "research" || i.layer === "preprint"); }
    };
    if (h === "region") return {
      key: h, title: "Philippines & Southeast Asia",
      note: "Current items about the region, or research by authors at institutions in the region.",
      filter: function (i) { return isCurrent(i) && i.region; }
    };
    if (h === "editions") return { key: h, title: "Past Editions", editionsList: true,
      note: "Every day's reading list is saved. Pick a date to see the list as it appeared that day." };
    if (h.indexOf("edition/") === 0) return { key: "editions", edition: h.slice(8) };
    if (h === "archive") return {
      key: h, title: "Archive",
      note: "Everything from the past year, including items past their freshness window. Use the search box.",
      filter: function () { return true; }
    };
    if (h === "about") return { key: h, title: "About & Sources", about: true };
    if (h.indexOf("topic/") === 0) {
      var id = h.slice(6);
      return {
        key: h, title: topicName(id),
        note: "Current items tagged with this topic.",
        filter: function (i) { return isCurrent(i) && i.topics.indexOf(id) >= 0; }
      };
    }
    return {
      key: "today", title: "Today’s Dispatch",
      note: "Everything still inside its freshness window: 7 days for news, 14 for analysis, 30 for preprints, 60 for research and reports.",
      filter: isCurrent, showEditionsLink: true
    };
  }

  /* ---------------- Story cards ---------------- */

  function storyNode(item, lead, ctx) {
    ctx = ctx || {};
    var kicker = el("p", { class: "kicker" }, [
      document.createTextNode(item.type),
      el("span", { class: "src", text: " · " + item.source })
    ]);
    var link = el("a", { href: item.url, rel: "noopener", target: "_blank", text: item.title });
    var head = el("h3", { class: "headline" }, [link]);

    var meta = el("div", { class: "meta" }, [
      el("time", {
        datetime: item.published,
        text: (item.date_estimated ? "Added " : "") + fmtDate(new Date(item.published)),
        title: item.date_estimated ? "The source gives no date; this is the day it first appeared here." : ""
      })
    ]);
    if (ctx.edition) {
      if (ctx.isNew) meta.appendChild(el("span", { class: "badge new", text: "New in this edition" }));
    } else {
      var f = freshness(item);
      if (f) meta.appendChild(el("span", { class: "badge " + f.cls, text: f.text }));
    }
    (item.labels || []).forEach(function (l) { meta.appendChild(el("span", { class: "badge warn", text: l })); });
    meta.appendChild(el("span", { class: "badge free", text: item.access || "Free to read" }));

    var tags = el("div", { class: "tags" });
    item.topics.forEach(function (t) { tags.appendChild(el("a", { href: "#topic/" + t, text: topicName(t) })); });
    if (item.region && state.region) tags.appendChild(el("a", { href: "#region", text: state.region.name }));

    return el("article", { class: "story" + (lead ? " lead" : "") }, [kicker, head, meta, tags]);
  }

  function renderChips() {
    var box = $("type-chips");
    box.textContent = "";
    ["All"].concat(TYPES).forEach(function (t) {
      var b = el("button", { type: "button", class: "chip", "aria-pressed": String(state.type === t), text: t });
      b.addEventListener("click", function () { state.type = t; render(); });
      box.appendChild(b);
    });
  }

  function renderTopicMenu() {
    var ul = $("topic-links");
    ul.textContent = "";
    [["core", "Core"], ["context", "Context"]].forEach(function (g) {
      ul.appendChild(el("li", { class: "group", text: g[1] }));
      state.topics.filter(function (t) { return t.group === g[0]; }).forEach(function (t) {
        ul.appendChild(el("li", {}, [el("a", { href: "#topic/" + t.id, text: t.name })]));
      });
    });
  }

  function markNav(key) {
    document.querySelectorAll(".sections a").forEach(function (a) {
      var target = a.getAttribute("href").slice(1);
      if (target === key) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    var d = document.querySelector(".topics-menu details");
    if (d) d.open = false;
  }

  function show(mode) {
    // mode: "stories" | "about" | "editions"
    $("filters").hidden = mode !== "stories";
    $("stories").hidden = mode !== "stories";
    $("about-page").hidden = mode !== "about";
    $("editions-page").hidden = mode !== "editions";
    $("edition-nav").hidden = true;
    $("empty").hidden = true;
  }

  function applyFilters(list) {
    var q = state.query.toLowerCase();
    return list.filter(function (i) {
      return (state.type === "All" || i.type === state.type) &&
             (!q || (i.title + " " + i.source).toLowerCase().indexOf(q) >= 0);
    });
  }

  function renderList(list, opts) {
    opts = opts || {};
    var box = $("stories");
    box.textContent = "";
    var empty = $("empty");
    if (!list.length) {
      empty.hidden = false;
      empty.textContent = opts.emptyText || (state.items.length
        ? "Nothing here right now. Try another section, clear the filters, or check Past Editions."
        : "The first edition hasn't been published yet. It appears after the daily update runs.");
      return;
    }
    empty.hidden = true;
    list.forEach(function (item, idx) {
      box.appendChild(storyNode(item, idx === 0 && !opts.noLead,
        opts.edition ? { edition: true, isNew: opts.newIds[item.id] } : null));
    });
  }

  /* ---------------- Main render ---------------- */

  function render() {
    var sec = sectionFor(location.hash);
    markNav(sec.key);

    if (sec.edition) { renderEdition(sec.edition); return; }

    $("section-title").textContent = sec.title;
    $("section-note").textContent = sec.note || "";
    $("section-extra").textContent = "";

    if (sec.about) { show("about"); renderAbout($("about-page")); return; }
    if (sec.editionsList) { show("editions"); renderEditionsList(); return; }

    show("stories");
    renderChips();
    if (sec.showEditionsLink && state.editions && state.editions.length > 1) {
      $("section-extra").appendChild(el("a", { href: "#editions", text: "Browse past editions →" }));
    }
    renderList(applyFilters(state.items.filter(sec.filter)), { noLead: sec.key === "archive" });
  }

  /* ---------------- Past editions ---------------- */

  function renderEditionsList() {
    var box = $("editions-page");
    box.textContent = "";
    if (!state.editions || !state.editions.length) {
      box.appendChild(el("p", { class: "empty", text: "Past editions will appear here after the daily update runs." }));
      return;
    }
    var byMonth = {};
    var order = [];
    state.editions.forEach(function (e) {
      var m = new Date(e.date + "T12:00:00+08:00").toLocaleDateString("en-US", { timeZone: TZ, month: "long", year: "numeric" });
      if (!byMonth[m]) { byMonth[m] = []; order.push(m); }
      byMonth[m].push(e);
    });
    order.forEach(function (m) {
      box.appendChild(el("h3", { class: "month", text: m }));
      var ul = el("ul", { class: "edition-list" });
      byMonth[m].forEach(function (e) {
        ul.appendChild(el("li", {}, [
          el("a", { href: "#edition/" + e.date, text: longDate(e.date) }),
          el("span", { class: "edition-count", text: e.count + " items · " + e.new + " new" })
        ]));
      });
      box.appendChild(ul);
    });
  }

  function loadEdition(date) {
    if (state.editionCache[date]) return Promise.resolve(state.editionCache[date]);
    return getJSON("data/editions/" + date + ".json").then(function (d) {
      state.editionCache[date] = d;
      return d;
    });
  }

  function renderEdition(date) {
    $("section-title").textContent = "Edition of " + longDate(date);
    $("section-note").textContent = "Loading…";
    $("section-extra").textContent = "";
    show("stories");
    renderChips();
    $("stories").textContent = "";

    // previous / next links
    var nav = $("edition-nav");
    nav.textContent = "";
    var list = state.editions || [];
    var idx = -1;
    for (var i = 0; i < list.length; i++) if (list[i].date === date) idx = i;
    var newer = idx > 0 ? list[idx - 1] : null;
    var older = idx >= 0 && idx < list.length - 1 ? list[idx + 1] : null;
    nav.appendChild(older ? el("a", { href: "#edition/" + older.date, text: "← " + fmtDate(new Date(older.date + "T12:00:00+08:00")) }) : el("span"));
    nav.appendChild(el("a", { href: "#editions", text: "All editions" }));
    nav.appendChild(newer ? el("a", { href: "#edition/" + newer.date, text: fmtDate(new Date(newer.date + "T12:00:00+08:00")) + " →" }) : el("span"));
    nav.hidden = false;

    loadEdition(date).then(function (ed) {
      if (sectionFor(location.hash).edition !== date) return; // user moved on
      var newIds = {};
      (ed.new || []).forEach(function (id) { newIds[id] = true; });
      var items = ed.items.map(function (id) { return state.byId[id]; }).filter(Boolean);
      var missing = ed.items.length - items.length;
      items.sort(function (a, b) {
        if (!!newIds[b.id] !== !!newIds[a.id]) return newIds[b.id] ? 1 : -1;
        return a.published < b.published ? 1 : -1;
      });
      $("section-note").textContent = ed.items.length + " items on the site that day, " +
        (ed.new || []).length + " of them new." +
        (missing ? " " + missing + " older items have since left the archive." : "");
      renderList(applyFilters(items), { edition: true, newIds: newIds,
        emptyText: "No items match these filters in this edition." });
    }).catch(function () {
      $("section-note").textContent = "";
      $("empty").hidden = false;
      $("empty").textContent = "There is no saved edition for this date.";
    });
  }

  /* ---------------- About ---------------- */

  function para(text) { return el("p", { text: text }); }

  function renderAbout(box) {
    box.textContent = "";
    box.appendChild(el("h3", { text: "What this is" }));
    box.appendChild(para("The Change Dispatch collects timely, credible news and research on organizational change, AI at work, psychology and economics, with a section on the Philippines and Southeast Asia. It updates itself every morning, Manila time, and saves each day’s edition so readers can go back to it."));

    box.appendChild(el("h3", { text: "Inclusion policy" }));
    var rules = el("ul");
    [
      "Every item must be free to read, or it doesn't appear. Research papers appear only when a free legal copy exists, and the link goes to that copy.",
      "Sources must be established institutions: peer-reviewed journals, universities, government agencies, international organizations or established news organizations with editorial standards.",
      "Every item needs a clear publication date and a named author or institution.",
      "Never included: social media, personal blogs, newsletters, company press releases, content farms or anonymous sources.",
      "Preprints and working papers are labeled “Not yet peer-reviewed”. Opinion pieces are labeled “Opinion”. Retracted papers are excluded.",
      "The site links to and labels other people's work. It never republishes full articles or rewrites their claims."
    ].forEach(function (r) { rules.appendChild(el("li", { text: r })); });
    box.appendChild(rules);

    box.appendChild(el("h3", { text: "Source status (latest run)" }));
    if (!state.status) { box.appendChild(para("Status will appear after the first daily run.")); return; }
    if (!state.status.openalex_key_present) {
      box.appendChild(para("Note: the OpenAlex key was not available on the last run, so journal sources were skipped."));
    }
    var table = el("table");
    table.appendChild(el("thead", {}, [el("tr", {}, ["Source", "Type", "Status", "Kept", "Newest item"].map(function (h) {
      return el("th", { scope: "col", text: h });
    }))]));
    var tb = el("tbody");
    state.status.sources.forEach(function (s) {
      var st = s.ok ? (s.stale ? "Working, but nothing new in 60+ days" : "Working") : "Not working";
      var cls = s.ok && !s.stale ? "status-ok" : "status-bad";
      var tr = el("tr", {}, [
        el("td", { text: s.name }),
        el("td", { text: LAYER_NAMES[s.layer] || s.layer }),
        el("td", {}, [el("span", { class: cls, text: st })]),
        el("td", { text: String(s.kept) }),
        el("td", { text: s.newest_item ? fmtDate(new Date(s.newest_item)) : "—" })
      ]);
      if (!s.ok && s.error) tr.title = s.error;
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    box.appendChild(table);
    box.appendChild(para("The full list of sources, topics and keywords is public in the project's GitHub repository, in the config folder."));
  }

  /* ---------------- Start ---------------- */

  function getJSON(path) {
    return fetch(path + "?v=" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  $("today-date").textContent = new Date().toLocaleDateString("en-US",
    { timeZone: TZ, weekday: "long", year: "numeric", month: "long", day: "numeric" });

  $("search").addEventListener("input", function (e) { state.query = e.target.value.trim(); render(); });
  window.addEventListener("hashchange", function () { window.scrollTo(0, 0); render(); });

  Promise.all([
    getJSON("data/items.json").catch(function () { return null; }),
    getJSON("data/status.json").catch(function () { return null; }),
    getJSON("data/editions/index.json").catch(function () { return null; })
  ]).then(function (res) {
    var data = res[0];
    state.status = res[1];
    state.editions = res[2] ? res[2].editions : [];
    if (data) {
      state.items = data.items || [];
      state.items.forEach(function (i) { state.byId[i.id] = i; });
      state.topics = data.topics || [];
      state.region = data.region || null;
      state.generated = data.generated;
      $("updated").textContent = "Updated " + fmtDate(new Date(data.generated), true);
    } else {
      $("updated").textContent = "First edition coming soon";
    }
    renderTopicMenu();
    render();
  });
})();
