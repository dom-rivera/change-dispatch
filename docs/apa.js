/* APA 7 reference formatter for The Change Dispatch.
   Returns { html, text }: html uses <i> for italics (journal, volume,
   site names) and text is the plain version. Input fields are escaped. */
(function (root) {
  "use strict";

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
    });
  }

  // "Jean-Paul de la Cruz" -> "de la Cruz, J.-P."; "Wang, Jennifer" -> "Wang, J."
  function apaName(full) {
    full = String(full || "").replace(/\s+/g, " ").trim();
    if (!full) return "";
    var family, given;
    if (full.indexOf(",") > 0) {
      family = full.slice(0, full.indexOf(",")).trim();
      given = full.slice(full.indexOf(",") + 1).trim();
    } else {
      var parts = full.split(" ");
      if (parts.length === 1) return full;            // organisation or single name
      var suffix = "";
      if (/^(jr\.?|sr\.?|ii|iii|iv)$/i.test(parts[parts.length - 1])) suffix = parts.pop();
      var i = parts.length - 1;
      // keep particles with the family name: de, del, dela, van, von, da, di, le, la
      while (i > 1 && /^(de|del|dela|della|van|von|der|den|da|di|du|le|la|dos|das|bin|binti)$/i.test(parts[i - 1])) i--;
      family = parts.slice(i).join(" ") + (suffix ? ", " + suffix.replace(/\.?$/, ".") : "");
      given = parts.slice(0, i).join(" ");
    }
    var initials = given.split(/\s+/).filter(Boolean).map(function (g) {
      return g.split("-").map(function (h) {
        var ch = h.replace(/[^A-Za-zÀ-ÿ]/g, "").charAt(0);
        return ch ? ch.toUpperCase() + "." : "";
      }).filter(Boolean).join("-");
    }).filter(Boolean).join(" ");
    return initials ? family + ", " + initials : family;
  }

  function authorList(names) {
    var a = (names || []).map(apaName).filter(Boolean);
    if (!a.length) return "";
    if (a.length === 1) return a[0];
    if (a.length === 2) return a[0] + ", & " + a[1];
    if (a.length <= 20) return a.slice(0, -1).join(", ") + ", & " + a[a.length - 1];
    return a.slice(0, 19).join(", ") + ", . . . " + a[a.length - 1];
  }

  function endWithPeriod(s) {
    s = String(s).trim();
    return /[.?!]$/.test(s) ? s : s + ".";
  }

  function doiUrl(doi) {
    if (!doi) return "";
    doi = String(doi).trim();
    if (/^https?:\/\/(dx\.)?doi\.org\//i.test(doi)) return doi.replace(/^http:/i, "https:").replace("dx.doi.org", "doi.org");
    if (/^10\.\d{4,}\//.test(doi)) return "https://doi.org/" + doi;
    return "";
  }

  function datePart(item, kind) {
    var d = new Date(item.published);
    if (isNaN(d)) return "(n.d.)";
    var opts = { timeZone: "Asia/Manila" };
    var y = d.toLocaleString("en-US", Object.assign({ year: "numeric" }, opts));
    if (kind === "news") {
      var m = MONTHS[Number(d.toLocaleString("en-US", Object.assign({ month: "numeric" }, opts))) - 1];
      var day = d.toLocaleString("en-US", Object.assign({ day: "numeric" }, opts));
      return "(" + y + ", " + m + " " + day + ")";
    }
    return "(" + y + ")";
  }

  function format(item) {
    var c = item.cite || {};
    var kind = c.kind || ({ research: "journal", preprint: "preprint", institutional: "report" }[item.layer] || "news");
    var authors = authorList(c.authors);
    var date = datePart(item, kind);
    var title = String(item.title || "").trim();
    var container = c.container || item.source || "";
    var link = doiUrl(c.doi) || item.url;
    var h = [], t = [];

    function add(htmlPart, textPart) { h.push(htmlPart); t.push(textPart === undefined ? htmlPart : textPart); }

    // Author and date (APA moves the title first when there is no author)
    if (authors) {
      add(esc(endWithPeriod(authors)), endWithPeriod(authors));
      add(date + ".");
    }

    if (kind === "journal") {
      if (!authors) { add(esc(endWithPeriod(title)), endWithPeriod(title)); add(date + "."); }
      else add(esc(endWithPeriod(title)), endWithPeriod(title));
      var src = "<i>" + esc(container) + "</i>", srcT = container;
      if (c.volume) {
        src += ", <i>" + esc(c.volume) + "</i>"; srcT += ", " + c.volume;
        if (c.issue) { src += "(" + esc(c.issue) + ")"; srcT += "(" + c.issue + ")"; }
      }
      if (c.first_page) {
        var pages = c.first_page + (c.last_page && c.last_page !== c.first_page ? "–" + c.last_page : "");
        src += ", " + esc(pages); srcT += ", " + pages;
      }
      add(src + ".", srcT + ".");
    } else if (kind === "preprint" || kind === "working_paper") {
      var label = kind === "preprint" ? " [Preprint]" : " [Working paper]";
      var tt = String(title).replace(/[.]$/, "") + label + ".";
      if (!authors) { add(esc(tt), tt); add(date + "."); } else add(esc(tt), tt);
      var pub = kind === "preprint" ? (container || "PsyArXiv") : (c.publisher || container);
      add(esc(endWithPeriod(pub)), endWithPeriod(pub));
    } else if (kind === "report") {
      // Reports and working papers from institutions: title in italics
      if (!authors) {
        add(esc(endWithPeriod(container)), endWithPeriod(container));
        add(date + ".");
      }
      add("<i>" + esc(endWithPeriod(title)) + "</i>", endWithPeriod(title));
      if (authors) add(esc(endWithPeriod(container)), endWithPeriod(container));
    } else {
      // News and web articles: site name in italics
      if (!authors) { add(esc(endWithPeriod(title)), endWithPeriod(title)); add(date + "."); }
      else add(esc(endWithPeriod(title)), endWithPeriod(title));
      add("<i>" + esc(container) + "</i>.", container + ".");
    }

    add(esc(link), link);
    return { html: h.join(" "), text: t.join(" "), missingAuthors: !authors };
  }

  var api = { format: format, apaName: apaName, authorList: authorList };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.APA = api;
})(this);
