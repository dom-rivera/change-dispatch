// Run with: node tests/apa.test.js
const assert = require("assert");
const APA = require("../docs/apa.js");

assert.strictEqual(APA.apaName("Jennifer Wang"), "Wang, J.");
assert.strictEqual(APA.apaName("Ma. Regina M. Hechanova"), "Hechanova, M. R. M.");
assert.strictEqual(APA.apaName("Jean-Paul Sartre"), "Sartre, J.-P.");
assert.strictEqual(APA.apaName("Juan de la Cruz"), "de la Cruz, J.");
assert.strictEqual(APA.apaName("Wang, Jennifer"), "Wang, J.");
assert.strictEqual(APA.apaName("Reuters"), "Reuters");
assert.strictEqual(APA.apaName("Agence France-Presse"), "Agence France-Presse");
assert.strictEqual(APA.apaName("Philippine News Agency"), "Philippine News Agency");
assert.strictEqual(APA.apaName("Jessica Bhuiyan"), "Bhuiyan, J.");
assert.strictEqual(APA.authorList(["A B", "C D"]), "B, A., & D, C.");
assert.strictEqual(APA.authorList(["A B", "C D", "E F"]), "B, A., D, C., & F, E.");
const many = Array.from({ length: 22 }, (_, i) => "Given Fam" + i);
assert.ok(APA.authorList(many).includes(", . . . Fam21, G.") && APA.authorList(many).split(", G.").length === 21);

const journal = APA.format({
  title: "Readiness for change during digital transformation", published: "2026-10-05T00:00:00Z",
  layer: "research", source: "Journal of Change Management", url: "https://x.org/a",
  cite: { kind: "journal", authors: ["Maria Santos", "Jose Reyes"], container: "Journal of Change Management",
          volume: "26", issue: "3", first_page: "201", last_page: "225", doi: "https://doi.org/10.1080/14697017.2026.1" }
});
assert.strictEqual(journal.text, "Santos, M., & Reyes, J. (2026). Readiness for change during digital transformation. Journal of Change Management, 26(3), 201–225. https://doi.org/10.1080/14697017.2026.1");
assert.ok(journal.html.includes("<i>Journal of Change Management</i>, <i>26</i>(3)"));

const news = APA.format({
  title: "PH jobless rate inched up to 5.4% in Sept", published: "2026-11-09T02:00:00Z", layer: "news",
  source: "Inquirer Business", url: "https://business.inquirer.net/1",
  cite: { kind: "news", authors: ["Ana Cruz"], container: "Inquirer Business" }
});
assert.strictEqual(news.text, "Cruz, A. (2026, November 9). PH jobless rate inched up to 5.4% in Sept. Inquirer Business. https://business.inquirer.net/1");

const noAuthor = APA.format({ title: "AI clog", published: "2026-11-09T02:00:00Z", layer: "news",
  source: "The Guardian (Technology)", url: "https://g.com/x", cite: { kind: "news", authors: [], container: "The Guardian" } });
assert.strictEqual(noAuthor.text, "AI clog. (2026, November 9). The Guardian. https://g.com/x");
assert.ok(noAuthor.missingAuthors);

const pre = APA.format({ title: "AI Grief at Work", published: "2026-11-06T00:00:00Z", layer: "preprint",
  source: "PsyArXiv", url: "https://osf.io/x", cite: { kind: "preprint", authors: ["Lee Kim"], container: "PsyArXiv", doi: "10.31234/osf.io/abc" } });
assert.strictEqual(pre.text, "Kim, L. (2026). AI Grief at Work [Preprint]. PsyArXiv. https://doi.org/10.31234/osf.io/abc");

const xss = APA.format({ title: "<img src=x onerror=alert(1)>", published: "2026-11-06T00:00:00Z", layer: "news",
  source: "S", url: "https://x.org", cite: { kind: "news", authors: [], container: "S" } });
assert.ok(!xss.html.includes("<img"));

console.log("APA tests passed");
