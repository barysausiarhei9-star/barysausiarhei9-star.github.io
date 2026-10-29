/* Optional preferences for Pereborsh literary text only. */
(() => {
  "use strict";

  // Bookmarks are independent of article typography controls.
  const bookmarkKey = "schrodinger:pereborsh-bookmark:v1";
  const chapterPath = /^\/proza\/pereborsh\/glava-(0[1-9]|1[0-9]|2[0-7])\/$/;
  const resume = document.getElementById("novel-resume");

  function refreshBookmark() {
    const chapter = location.pathname.match(chapterPath);
    if (chapter && document.querySelector("article#novel-text")) {
      try {
        localStorage.setItem(bookmarkKey, String(Number(chapter[1])));
      } catch {
        // Reading remains available when storage cannot be written.
      }
    }
    if (!resume || location.pathname !== "/proza/pereborsh/") return;
    resume.hidden = true;
    resume.replaceChildren();
    let stored;
    try {
      stored = localStorage.getItem(bookmarkKey);
    } catch {
      return;
    }
    // Accept only the canonical integer representation written above.
    if (!/^(?:[1-9]|1[0-9]|2[0-7])$/.test(stored)) return;
    const destination = `/proza/pereborsh/glava-${stored.padStart(2, "0")}/`;
    const entry = Array.from(document.querySelectorAll(".novel-toc > li > a"))
      .find(link => link.getAttribute("href") === destination);
    if (!entry || !entry.textContent.trim()) return;

    const link = document.createElement("a");
    link.href = destination + "#novel-text";
    link.textContent = "Продолжить чтение";
    const title = document.createElement("p");
    title.textContent = entry.textContent;
    const note = document.createElement("p");
    note.textContent = "Последняя открытая глава сохранена в этом браузере.";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = "Сбросить";
    reset.setAttribute("aria-label", "Сбросить последнюю открытую главу");
    reset.addEventListener("click", () => {
      try {
        localStorage.removeItem(bookmarkKey);
      } catch {
        // Re-read storage so a failed reset never falsely reports success.
      }
      refreshBookmark();
      const focusTarget = resume.hidden
        ? document.querySelector(".novel-start a") : resume.querySelector("button");
      if (focusTarget) focusTarget.focus();
    });
    resume.append(link, title, note, reset);
    resume.hidden = false;
  }
  refreshBookmark();
  window.addEventListener("pageshow", refreshBookmark);

  const article = document.getElementById("novel-text");
  const controls = document.getElementById("reading-preferences");
  if (!article || !controls) return;

  const size = document.getElementById("reading-size");
  const width = document.getElementById("reading-width");
  const reset = document.getElementById("reading-reset");
  if (!size || !width || !reset) return;

  const key = "schrodinger:pereborsh-reading:v1";
  const defaults = { size: "original", width: "original" };
  const valid = value => value && typeof value === "object" && !Array.isArray(value)
    && ["original", "larger", "largest"].includes(value.size)
    && ["original", "narrower"].includes(value.width);

  function apply(value) {
    size.value = value.size;
    width.value = value.width;
    if (value.size === "original") article.removeAttribute("data-reading-size");
    else article.dataset.readingSize = value.size;
    if (value.width === "original") article.removeAttribute("data-reading-width");
    else article.dataset.readingWidth = value.width;
  }

  function save(value) {
    try {
      if (value.size === "original" && value.width === "original") localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify({ size: value.size, width: value.width }));
    } catch {
      // Preferences still work on this page when browser storage is unavailable.
    }
  }

  let initial = defaults;
  try {
    const stored = JSON.parse(localStorage.getItem(key));
    if (valid(stored)) initial = stored;
  } catch {
    // Missing, inaccessible or malformed storage leaves the original typography.
  }
  apply(initial);

  function change() {
    const value = { size: size.value, width: width.value };
    if (!valid(value)) return;
    apply(value);
    save(value);
  }
  size.addEventListener("change", change);
  width.addEventListener("change", change);
  reset.addEventListener("click", () => {
    apply(defaults);
    save(defaults);
  });
  controls.hidden = false;
})();
