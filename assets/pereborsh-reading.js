/* Optional preferences for Pereborsh literary text only. */
(() => {
  "use strict";

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
