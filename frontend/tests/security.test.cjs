const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.value = "all"; this.style = {}; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  addEventListener() {}
  set innerHTML(_) { throw new Error("Untrusted HTML insertion"); }
}

function dashboard() {
  const elements = new Map();
  const context = vm.createContext({
    URL, URLSearchParams, Intl,
    window: { APP_CONFIG: { API_BASE: "http://localhost:5000/api/v1" } },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, new Element("div"));
        return elements.get(id);
      },
      createElement: (tag) => new Element(tag),
    },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../public/js/dashboard.js"), "utf8"), context);
  return { context, elements };
}

test("job content is rendered literally and script URLs are not linked", () => {
  const { context, elements } = dashboard();
  const attack = '<img src=x onerror="alert(1)">';
  context.renderJobsTable({ total: 1, items: [{ title: attack, company: attack, location: attack, source: attack, role_family: attack, url: "javascript:alert(1)" }] });
  const row = elements.get("jobsTableBody").children[0];
  assert.equal(row.children.length, 5);
  for (const cell of row.children) {
    assert.equal(cell.textContent, attack);
    assert.equal(cell.children.length, 0);
  }
});

test("unsafe URL protocols and embedded credentials are blocked", () => {
  const { context } = dashboard();
  for (const url of ["javascript:alert(1)", "data:text/html,payload", "file:///etc/passwd", "//attacker.invalid", "https://user:password@example.com", "invalid", null]) {
    assert.equal(context.safeJobUrl(url), null);
  }
  assert.equal(context.safeJobUrl("https://hh.ru/vacancy/123"), "https://hh.ru/vacancy/123");
});

test("external links suppress referrer and opener access", () => {
  const { context, elements } = dashboard();
  context.renderJobsTable({ total: 1, items: [{ title: "Developer", url: "https://hh.ru/vacancy/123" }] });
  const link = elements.get("jobsTableBody").children[0].children[0].children[0];
  assert.equal(link.tag, "a");
  assert.equal(link.rel, "noopener noreferrer");
  assert.equal(link.href, "https://hh.ru/vacancy/123");
});
