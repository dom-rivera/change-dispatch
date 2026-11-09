/* The Change Dispatch: front-end.
   Reads data/items.json and data/status.json (written daily by
   scripts/fetch.py) and renders the sections. All text from feeds is
   inserted with textContent, never as HTML. */
(function () {
  "use strict";

  var DAY = 86400000;
  var TZ = "Asia/Manila";
  var TYPES = ["Peer-reviewed", "Preprint", "Institutional", "Expert analysis", "News"];

  var state = { items: [], topics: [], region: null, status: null, generated: null,
                type: "All", query: "" };

  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
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

  /* ---------------- Sections ---------------- */

  function coreIds() {
    return state.topics.filter(function (t) { return t.group === "core"; }).map(function (t) { return t.id; });
  }

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
    if (h === "archive") return {
      key: h, title: "Archive",
      note: "Everything from the past year, including items past their freshness window. Use the search box.",
      filter: function () { return true; }
    };
    if (h === "about") return { key: h, title: "About & sources", about: true };
    if (h.indexOf("topic/") === 0) {
      var id = h.slice(6);
      return {
        key: h, title: topicName(id),
        note: "Current items tagged with this topic.",
        filter: function (i) { return isCurrent(i) && i.topics.indexOf(id) >= 0; }
      };
    }
    return {
      key: "today", title: "Today's Dispatch",
      note: "Everything still inside its freshness window: 7 days for news, 14 for analysis, 30 for preprints, 60 for research and reports.",
      filter: isCurrent
    };
  }

  /* ---------------- Rendering ---------------- */

  function storyNode(item, lead) {
    var kicker = el("p", { class: "kicker" }, [
      document.createTextNode(item.type + " · "),
      el("span", { class: "src", text: item.source })
    ]);
    var link = el("a", { href: item.url, rel: "noopener", target: "_blank", text: item.title });
    var head = el(lead ? "h3" : "h3", { class: "headline" }, [link]);

    var meta = el("div", { class: "meta" }, [
      el("time", { datetime: item.published, text: fmtDate(new Date(item.published)) })
    ]);
    var f = freshness(item);
    if (f) meta.appendChild(el("span", { class: "badge " + f.cls, text: f.text }));
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

  function render() {
    var sec = sectionFor(location.hash);
    $("section-title").textContent = sec.title;
    $("section-note").textContent = sec.note || "";
    markNav(sec.key);

    var about = $("about-page");
    if (sec.about) {
      $("filters").hidden = true; $("stories").hidden = true; $("empty").hidden = true;
      about.hidden = false;
      renderAbout(about);
      return;
    }
    about.hidden = true; $("filters").hidden = false; $("stories").hidden = false;
    renderChips();

    var q = state.query.toLowerCase();
    var list = state.items.filter(sec.filter).filter(function (i) {
      return (state.type === "All" || i.type === state.type) &&
             (!q || (i.title + " " + i.source).toLowerCase().indexOf(q) >= 0);
    });

    var box = $("stories");
    box.textContent = "";
    var empty = $("empty");
    if (!list.length) {
      empty.hidden = false;
      empty.textContent = state.items.length
        ? "Nothing here right now. Try another section, clear the filters, or check the Archive."
        : "The first edition hasn't been published yet. It appears after the daily update runs.";
      return;
    }
    empty.hidden = true;
    list.forEach(function (item, idx) { box.appendChild(storyNode(item, idx === 0 && sec.key !== "archive")); });
  }

  function para(text) { return el("p", { text: text }); }

  function renderAbout(box) {
    box.textContent = "";
    box.appendChild(el("h3", { text: "What this is" }));
    box.appendChild(para("The Change Dispatch collects timely, credible news and research on organizational change, AI at work, psychology and economics, with a section on the Philippines and Southeast Asia. It updates itself every morning, Manila time."));

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
        el("td", { text: ({ research: "Peer-reviewed", preprint: "Preprint", institutional: "Institutional", analysis: "Expert analysis", news: "News" })[s.layer] || s.layer }),
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
    getJSON("data/status.json").catch(function () { return null; })
  ]).then(function (res) {
    var data = res[0];
    state.status = res[1];
    if (data) {
      state.items = data.items || [];
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
