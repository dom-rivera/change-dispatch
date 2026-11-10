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
    editions: null, editionCache: {}, notes: [], type: "All", query: ""
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
    if (h === "notes") return { key: h, title: "Editor\u2019s Notes", notesList: true,
      note: "A weekly note from the editor connecting the week\u2019s news and research to theory on change at work." };
    if (h.indexOf("note/") === 0) return { key: "notes", noteSlug: h.slice(5) };
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
    // Only plain web links become clickable (defence in depth; the fetcher checks too)
    var safe = /^https?:\/\/[^\s"'<>]+$/i.test(item.url || "");
    var link = el("a", { href: safe ? item.url : null, rel: "noopener noreferrer", target: "_blank", text: item.title });
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

    var cite = el("button", { type: "button", class: "cite-btn", "aria-expanded": "false", text: "Cite (APA 7)" });
    meta.appendChild(cite);

    var tags = el("div", { class: "tags" });
    item.topics.forEach(function (t) { tags.appendChild(el("a", { href: "#topic/" + t, text: topicName(t) })); });
    if (item.region && state.region) tags.appendChild(el("a", { href: "#region", text: state.region.name }));

    var article = el("article", { class: "story" + (lead ? " lead" : "") }, [kicker, head, meta, tags]);
    cite.addEventListener("click", function () { toggleCitation(article, item, cite); });
    return article;
  }

  /* ---------------- APA 7 citations ---------------- */

  function copyCitation(ref, button) {
    var done = function () {
      button.textContent = "Copied";
      setTimeout(function () { button.textContent = "Copy"; }, 1800);
    };
    try {
      if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
        // Rich text keeps the italics when pasted into Word or Google Docs
        navigator.clipboard.write([new ClipboardItem({
          "text/html": new Blob([ref.html], { type: "text/html" }),
          "text/plain": new Blob([ref.text], { type: "text/plain" })
        })]).then(done, function () { navigator.clipboard.writeText(ref.text).then(done); });
        return;
      }
      navigator.clipboard.writeText(ref.text).then(done);
    } catch (e) {
      button.textContent = "Select the text to copy";
    }
  }

  function toggleCitation(article, item, button) {
    var open = article.querySelector(".citation");
    if (open) {
      open.remove();
      button.setAttribute("aria-expanded", "false");
      return;
    }
    var ref = window.APA.format(item);
    var text = el("p", { class: "citation-text" });
    text.innerHTML = ref.html;   // built from escaped fields by apa.js
    var copy = el("button", { type: "button", class: "copy-btn", text: "Copy" });
    copy.addEventListener("click", function () { copyCitation(ref, copy); });
    var notes = ["APA 7 uses sentence case for article titles: lower-case words after the first, except proper nouns."];
    if (ref.missingAuthors) notes.unshift("No author was listed by the source, so the title comes first. Check the original for an author.");
    var panel = el("div", { class: "citation", role: "region", "aria-label": "APA 7 citation" }, [
      text,
      el("div", { class: "citation-actions" }, [copy, el("span", { class: "citation-note", text: notes.join(" ") })])
    ]);
    article.appendChild(panel);
    button.setAttribute("aria-expanded", "true");
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
    $("notes-page").hidden = mode !== "notes";
    $("note-box").hidden = true;
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

    if (sec.noteSlug) { show("notes"); renderNote(sec.noteSlug); return; }
    if (sec.notesList) { show("notes"); renderNotesList(); return; }
    if (sec.about) { show("about"); renderAbout($("about-page")); return; }
    if (sec.editionsList) { show("editions"); renderEditionsList(); return; }

    show("stories");
    renderChips();
    if (sec.key === "today") renderNoteBox();
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

  /* ---------------- Editor's Notes ---------------- */

  function noteMeta(n) {
    return "By " + n.author + " \u00b7 " + longDate(n.date) + " \u00b7 " + n.minutes + " min read";
  }

  function renderNoteBox() {
    var box = $("note-box");
    box.textContent = "";
    var n = state.notes[0];
    if (!n) return;
    box.appendChild(el("p", { class: "note-kicker", text: "Editor\u2019s Note" }));
    box.appendChild(el("h3", { class: "note-box-title" }, [el("a", { href: "#note/" + n.slug, text: n.title })]));
    box.appendChild(el("p", { class: "note-box-summary", text: n.summary }));
    box.appendChild(el("p", { class: "note-box-meta" }, [
      document.createTextNode(noteMeta(n) + " \u00b7 "),
      el("a", { href: "#note/" + n.slug, text: "Read the note \u2192" })
    ]));
    box.hidden = false;
  }

  function renderNotesList() {
    var box = $("notes-page");
    box.textContent = "";
    if (!state.notes.length) {
      box.appendChild(el("p", { class: "empty", text: "The first Editor\u2019s Note is coming soon." }));
      return;
    }
    state.notes.forEach(function (n) {
      box.appendChild(el("article", { class: "note-item" }, [
        el("h3", { class: "headline" }, [el("a", { href: "#note/" + n.slug, text: n.title })]),
        el("p", { class: "note-box-summary", text: n.summary }),
        el("p", { class: "note-box-meta", text: noteMeta(n) })
      ]));
    });
  }

  function renderNote(slug) {
    var box = $("notes-page");
    box.textContent = "";
    var n = null;
    state.notes.forEach(function (x) { if (x.slug === slug) n = x; });
    if (!n) {
      $("section-title").textContent = "Editor\u2019s Notes";
      $("section-note").textContent = "";
      box.appendChild(el("p", { class: "empty", text: "This note could not be found. It may have been moved or removed." }));
      box.appendChild(el("p", {}, [el("a", { href: "#notes", text: "All notes" })]));
      return;
    }
    $("section-title").textContent = n.title;
    $("section-note").textContent = noteMeta(n);
    $("section-extra").textContent = "";
    var body = el("div", { class: "note-body" });
    body.innerHTML = n.html;   // built by scripts/build_notes.py: raw HTML escaped, only http(s) links
    box.appendChild(el("p", { class: "note-kicker", text: "Editor\u2019s Note" }));
    box.appendChild(body);
    box.appendChild(el("p", { class: "note-footer" }, [
      document.createTextNode("Views are the editor\u2019s own. "),
      el("a", { href: "#notes", text: "All notes" }),
      document.createTextNode(" \u00b7 "),
      el("a", { href: "#today", text: "Today\u2019s Dispatch" })
    ]));
  }

  /* ---------------- About ---------------- */

  function para(text) { return el("p", { text: text }); }

  var REPO = "https://github.com/dom-rivera/change-dispatch";

  function link(href, text) { return el("a", { href: href, rel: "noopener", target: "_blank", text: text }); }

  function renderAbout(box) {
    box.textContent = "";

    box.appendChild(el("h3", { text: "About the editor" }));
    var bio = el("p", { text: "Dom Rivera is a Registered Psychometrician and a Master of Arts in Psychology graduate candidate at Lyceum of the Philippines University \u2013 Batangas, where his thesis examines AI change readiness and organizational change. He works in HR shared services and previously taught psychology at the college level. He started The Change Dispatch to follow new research and news on how people respond to change at work, and to keep that reading list open to anyone." });
    box.appendChild(el("div", { class: "editor" }, [
      el("p", { class: "editor-name", text: "Dom Rivera" }),
      el("p", { class: "editor-role", text: "Editor \u00b7 Registered Psychometrician" }),
      bio,
      el("p", { class: "editor-links" }, [link("https://www.linkedin.com/in/dom-joseph-rivera", "LinkedIn")]),
      para("The editor chooses the sources, topics and rules. The daily collection is automated and applies those rules the same way every day; the editor reviews corrections and source suggestions.")
    ]));

    box.appendChild(el("h3", { text: "Corrections and suggestions" }));
    var help = el("p");
    help.appendChild(document.createTextNode("Found a broken link, a wrong label or an unreliable item? "));
    help.appendChild(link(REPO + "/issues/new?template=correction.yml", "Report a correction"));
    help.appendChild(document.createTextNode(". Know a free, reputable source we should add? "));
    help.appendChild(link(REPO + "/issues/new?template=suggest-source.yml", "Suggest a source"));
    help.appendChild(document.createTextNode(". Both forms are on GitHub and need a free GitHub account. Every change to the site is public in the repository history."));
    box.appendChild(help);

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

  /* Live clock in Manila time; the date line also rolls over at midnight. */
  function tick() {
    var now = new Date();
    $("today-date").textContent = now.toLocaleDateString("en-US",
      { timeZone: TZ, weekday: "long", year: "numeric", month: "long", day: "numeric" });
    var clock = $("clock");
    clock.textContent = now.toLocaleTimeString("en-US",
      { timeZone: TZ, hour: "numeric", minute: "2-digit", second: "2-digit" });
    clock.setAttribute("datetime", now.toISOString());
  }
  tick();
  setInterval(tick, 1000);

  $("search").addEventListener("input", function (e) { state.query = e.target.value.trim(); render(); });
  window.addEventListener("hashchange", function () { window.scrollTo(0, 0); render(); });

  Promise.all([
    getJSON("data/items.json").catch(function () { return null; }),
    getJSON("data/status.json").catch(function () { return null; }),
    getJSON("data/editions/index.json").catch(function () { return null; }),
    getJSON("data/notes.json").catch(function () { return null; })
  ]).then(function (res) {
    var data = res[0];
    state.status = res[1];
    state.editions = res[2] ? res[2].editions : [];
    state.notes = res[3] ? res[3].notes || [] : [];
    if (data) {
      state.items = data.items || [];
      state.items.forEach(function (i) { state.byId[i.id] = i; });
      state.topics = data.topics || [];
      state.region = data.region || null;
      state.generated = data.generated;
      $("updated").textContent = "Updated " + fmtDate(new Date(data.generated), true);
      // Tell readers if the daily update has not run for more than a day
      var hours = (Date.now() - new Date(data.generated).getTime()) / 3600000;
      if (hours > 30) {
        var stale = $("stale");
        stale.textContent = "This edition was last updated " + Math.floor(hours / 24 >= 1 ? hours / 24 : hours) +
          (hours >= 48 ? " days" : hours >= 24 ? " day" : " hours") +
          " ago. Today\u2019s update is delayed; the items below may be out of date.";
        stale.hidden = false;
      }
    } else {
      $("updated").textContent = "First edition coming soon";
    }
    renderTopicMenu();
    render();
  });
})();
