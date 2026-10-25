/* Browser-only search. CommonJS export keeps the same functions testable in Node. */
(function () {
  "use strict";
  const normalize = text => text.normalize("NFC").toLowerCase().replace(/ё/g, "е");

  function search(pages, query) {
    const input = normalize(query).trim();
    const terms = input.match(/"[^"]+"|[^\s"]+/g) || [];
    const tokens = [...new Set(terms.map(term => term.replace(/^"|"$/g, "")).filter(Boolean))];
    if (!tokens.length) return [];
    const phrase = tokens.join(" ");
    return pages.flatMap(page => {
      const title = normalize(page.title);
      const body = normalize(page.text);
      if (!tokens.every(term => title.includes(term) || body.includes(term))) return [];
      const score = (title.includes(phrase) ? 100 : 0) + (body.includes(phrase) ? 20 : 0) +
        tokens.reduce((sum, term) => sum + (title.includes(term) ? 10 : 0), 0);
      return [{ ...page, score }];
    }).sort((a, b) => b.score - a.score || (a.url < b.url ? -1 : a.url > b.url ? 1 : 0));
  }

  function snippet(text, query, emptyText) {
    if (!text) return emptyText || "Текст произведения представлен изображением. Поиск доступен по названию.";
    const terms = normalize(query).match(/[^\s"]+/g) || [];
    const positions = terms.map(term => normalize(text).indexOf(term)).filter(i => i >= 0);
    let start = Math.max(0, (positions.length ? Math.min(...positions) : 0) - 60);
    if (start) {
      const boundary = text.indexOf(" ", start);
      if (boundary >= 0 && boundary < start + 30) start = boundary + 1;
    }
    const end = Math.min(text.length, start + 220);
    return (start ? "…" : "") + text.slice(start, end).trim() + (end < text.length ? "…" : "");
  }

  function renderResults(document, container, results, query, emptyText) {
    container.replaceChildren();
    for (const page of results) {
      const item = document.createElement("li");
      const heading = document.createElement("h2");
      const link = document.createElement("a");
      link.href = page.url;
      link.textContent = page.title;
      const excerpt = document.createElement("p");
      // Text nodes escape both literary text and queries; never interpolate HTML.
      excerpt.textContent = snippet(page.text, query, emptyText);
      heading.append(link);
      item.append(heading, excerpt);
      container.append(item);
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { normalize, search, snippet, renderResults };
  }
  if (typeof document === "undefined") return;
  const form = document.getElementById("search-form");
  if (!form) return;
  const english = document.documentElement.lang === "en";
  const messages = english ? {
    empty: "Enter a title or words from the text.",
    loading: "Searching…",
    found: count => `Found: ${count}`,
    none: "No results. Try different words or part of a word.",
    error: "Could not load search. Please try again.",
    noText: "Body text is unavailable. Search is available by title."
  } : null;
  const input = document.getElementById("search-query");
  const status = document.getElementById("search-status");
  const container = document.getElementById("search-results");
  let index;
  let revision = 0;
  let timer;
  async function update() {
    const current = ++revision;
    const query = input.value.trim();
    const url = new URL(location.href);
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    container.replaceChildren();
    if (!query) {
      status.textContent = messages ? messages.empty : "Введите название или слова из текста.";
      return;
    }
    status.textContent = messages ? messages.loading : "Поиск…";
    try {
      if (!index) index = fetch(english ? "/assets/search-index-en.json" : "/assets/search-index.json").then(response => {
        if (!response.ok) throw new Error("Index unavailable");
        return response.json();
      });
      const data = await index;
      if (current !== revision) return;
      const results = search(data.pages, query);
      renderResults(document, container, results, query, messages && messages.noText);
      status.textContent = messages ? (results.length ? messages.found(results.length) : messages.none) : results.length ? `Найдено: ${results.length}` :
        "Ничего не найдено. Попробуйте другие слова или часть слова.";
    } catch {
      index = null;
      if (current === revision) status.textContent = messages ? messages.error : "Не удалось загрузить поиск. Повторите попытку.";
    }
  }
  form.addEventListener("submit", event => {
    event.preventDefault();
    clearTimeout(timer);
    update();
  });
  input.addEventListener("input", () => {
    ++revision;
    clearTimeout(timer);
    timer = setTimeout(update, 150);
  });
  input.value = new URLSearchParams(location.search).get("q") || "";
  update();
})();
