const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { search, snippet, renderResults } = require("../assets/search.js");
const { pages } = JSON.parse(readFileSync(join(__dirname, "../assets/search-index.json"), "utf8"));
const url = path => "https://schrodingercat.org" + path;
const english = JSON.parse(readFileSync(join(__dirname, "../assets/search-index-en.json"), "utf8")).pages;

test("English titles and available bodies are searchable with language isolation", () => {
  assert.equal(english.length, 32);
  assert.equal(search(english, "THE FORMULA OF GOD")[0].url, url("/en/articles/the-formula-of-god/"));
  assert.ok(search(english, '"information possessing a binary code"').some(p =>
    p.url === url("/en/articles/the-formula-of-god/")));
  for (const page of english) {
    assert.equal(page.language, "en");
    assert.ok(page.url.startsWith(url("/en/")));
    assert.ok(search(english, page.title).some(p => p.url === page.url));
    const words = page.text.split(/\s+/).slice(0, 8).join(" ").replaceAll('"', '');
    assert.ok(search(english, words).some(p => p.url === page.url));
  }
  assert.deepEqual(search(english, "ФОРМУЛА БОГА"), []);
  assert.deepEqual(search(pages, "information possessing a binary code"), []);
  assert.deepEqual(search(english, ""), []);
  assert.deepEqual(search(english, "unfindablequeryxyz"), []);
  assert.ok(search(pages, "cat").every(p => p.language === "ru"));
  assert.equal(snippet("", "", "No body text."), "No body text.");
});

test("Russian title, case, Cyrillic partial text, ё/е and title relevance", () => {
  assert.equal(search(pages, "ФОРМУЛА БОГА")[0].url, url("/articles/formula-boga/"));
  assert.ok(search(pages, "двоичн").some(p => p.url === url("/articles/formula-boga/")));
  assert.ok(search(pages, "ЖИЛ ДА БЫЛ ОДИН КОРОЛЬ").some(p => p.url === url("/poeziya/a-koronu/")));
  assert.deepEqual(search(pages, "ШРЁДИНГЕРА"), search(pages, "шредингера"));
});

test("A HINT is searchable by title and supplied text in both languages", () => {
  assert.equal(search(pages, "Подсказка")[0].url, url("/articles/a-hint/"));
  assert.ok(search(pages, '"координата этой точки МИНУС ОДИН"').some(p => p.url === url("/articles/a-hint/")));
  assert.equal(search(english, "A HINT")[0].url, url("/en/articles/a-hint/"));
  assert.ok(search(english, '"a decrease in that magnitude"').some(p => p.url === url("/en/articles/a-hint/")));
});

test("DISSECTION OF THE THEORY OF RELATIVITY is searchable by title and supplied text in both languages", () => {
  assert.equal(search(pages, "ПРЕПАРАЦИЯ ТЕОРИИ ОТНОСИТЕЛЬНОСТИ")[0].url, url("/articles/dissection-of-the-theory-of-relativity/"));
  assert.ok(search(pages, '"его мультипликацией"').some(p => p.url === url("/articles/dissection-of-the-theory-of-relativity/")));
  assert.equal(search(english, "DISSECTION OF THE THEORY OF RELATIVITY")[0].url, url("/en/articles/dissection-of-the-theory-of-relativity/"));
  assert.ok(search(english, '"its multiplication"').some(p => p.url === url("/en/articles/dissection-of-the-theory-of-relativity/")));
});

test("MOVEMENT is searchable by title and final paragraph in both languages", () => {
  assert.equal(search(pages, "Движение")[0].url, url("/articles/movement/"));
  assert.ok(search(pages, '"антиводород исследовал"').some(p => p.url === url("/articles/movement/")));
  assert.equal(search(english, "MOVEMENT")[0].url, url("/en/articles/movement/"));
  assert.ok(search(english, '"who have studied antihydrogen"').some(p => p.url === url("/en/articles/movement/")));
});

test("Meow is searchable by title, formula and final sentence in both languages", () => {
  for (const [index, prefix, last] of [[pages, "", "На этом, пожалуй, остановлюсь"],
    [english, "/en", "I think I shall stop here"]]) {
    const target = url(prefix + "/articles/meow/");
    assert.equal(search(index, "Meow")[0].url, target);
    assert.ok(search(index, '"mc2 + (i2)mc2"').some(p => p.url === target));
    assert.ok(search(index, '"' + last + '"').some(p => p.url === target));
  }
});

test("quoted phrases, unordered AND terms, partial matches and empty queries", () => {
  const fixture = [{ url: url("/one/"), title: "Кошка", text: "белая кошка читает книгу" },
    { url: url("/two/"), title: "Книга", text: "кошка белая читает стихи" }];
  assert.deepEqual(search(fixture, '"белая кошка"').map(p => p.url), [url("/one/")]);
  assert.equal(search(fixture, "чит кни").length, 2); // title and body both participate
  assert.equal(search(fixture, '"кошка читает" кни').length, 1);
  assert.equal(search(fixture, "кошка отсутствует").length, 0);
  for (const query of ["", "   ", '""']) assert.deepEqual(search(fixture, query), []);
  assert.deepEqual(search(fixture, "невозможныйзапрос"), []);
});

test("every Pereborsh chapter and introduction searchable by actual body text", () => {
  const chapters = pages.filter(p => /\/proza\/pereborsh\/(glava-\d+|vstuplenie)\/$/.test(p.url));
  assert.equal(chapters.length, 28);
  for (const page of chapters) {
    const phrase = page.text.split('"').find(part => part.length >= 25).slice(0, 80).trim();
    assert.ok(search(pages, '"' + phrase + '"').some(p => p.url === page.url), page.url);
  }
});

test("image-only works have title search without fabricated text; no boilerplate", () => {
  const page = search(pages, "ЭНДЕМИК").find(p => p.url === url("/poeziya/endemik/"));
  assert.equal(page.text, "");
  for (const query of ["Основная навигация", "Назад к поэзии", "Черно-белый постер"]) {
    assert.deepEqual(search(pages, query), [], query);
  }
  // Help explains the contents links; chapter navigation remains excluded.
  assert.deepEqual(search(pages, "Оглавление").map(p => p.url), [url("/help/")]);
});

test("brief snippets centered on matches and literal escaping through textContent", () => {
  const dangerous = '<img src=x onerror="alert(1)"> & <script>alert(2)</script>';
  const document = { createElement(tag) {
    return { tag, children: [], append(...children) { this.children.push(...children); },
      set innerHTML(_) { assert.fail("HTML interpolation must never be used"); } };
  } };
  const container = { children: [], replaceChildren() { this.children = []; },
    append(child) { this.children.push(child); } };
  renderResults(document, container, [{ title: dangerous, text: dangerous, url: url("/about/") }], "<img>");
  const [heading, excerpt] = container.children[0].children;
  assert.equal(heading.children[0].textContent, dangerous);
  assert.equal(heading.children[0].href, url("/about/"));
  assert.equal(excerpt.textContent, dangerous);
  assert.ok(snippet("начало ".repeat(100) + "уникальный" + " конец".repeat(100), "уникальный").includes("уникальный"));
  assert.ok(snippet("слово ".repeat(1000), "слово").length <= 222);
  assert.match(snippet("", "текст"), /изображением/);
});

test("Well, Would You Look at That is searchable by title and closing text in both languages", () => {
  for (const [index, prefix, title, last] of [
    [pages, "", "Это ж надо!", "вне зависимости от вашего на этот счет мнения"],
    [english, "/en", "Well, Would You Look at That!", "regardless of what you may think about it"]]) {
    const target = url(prefix + "/articles/eto-zh-nado/");
    assert.equal(search(index, title)[0].url, target);
    assert.ok(search(index, '"' + last + '"').some(p => p.url === target));
  }
});
