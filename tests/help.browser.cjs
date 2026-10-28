/* Local Chromium checks: navigation and layout only, not device speech playback.
   Run with an installed Playwright: node tests/help.browser.cjs
   Optional HELP_EVIDENCE_DIR keeps screenshots and the coverage report outside the repo. */
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const mime = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8" };

async function main() {
  const catalog = JSON.parse(await fs.readFile(path.join(root, "publication/catalog.json"), "utf8"));
  const pages = new Map(catalog.pages.map(page => [page.path, page]));
  assert.equal(pages.size, 94);
  assert.equal(catalog.navigation.items.length, 9);
  const server = http.createServer(async (request, response) => {
    try {
      let relative = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
      if (relative.endsWith("/")) relative += "index.html";
      const target = path.resolve(root, "." + relative);
      if (!target.startsWith(root + path.sep)) throw new Error("Outside root");
      const bytes = await fs.readFile(target);
      response.writeHead(200, { "Content-Type": mime[path.extname(target)] || "application/octet-stream" });
      response.end(bytes);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  const report = { registeredPages: 0, layouts: [], disclosures: 0, languageRoundTrips: 0 };
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const base = `http://127.0.0.1:${server.address().port}`;
    await context.route("**/*", route => new URL(route.request().url()).origin === base
      ? route.continue() : route.abort());
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const checkMenu = async route => {
      const language = pages.get(route).language;
      const links = await page.locator(".site-nav a").evaluateAll(nodes => nodes.map(a => ({
        href: a.getAttribute("href"), label: a.textContent, current: a.getAttribute("aria-current")
      })));
      const expected = catalog.navigation.items.map(item => ({
        href: item.targets[language], label: item.labels[language]
      }));
      assert.deepEqual(links.map(({ href, label }) => ({ href, label })), expected, route);
      // Independent expected active destination for every current registered route.
      const destination = route === "/articles/about/" ? "/about/" :
        expected.some(item => item.href === route) ? route :
        route.startsWith("/proza/") ? "/proza/" :
        route.startsWith("/poeziya/") ? "/poeziya/" :
        route.startsWith("/en/articles/") ? "/en/articles/" :
        route.startsWith("/articles/") ? "/articles/" : null;
      assert.ok(destination, `uncovered active state: ${route}`);
      assert.deepEqual(links.filter(a => a.current).map(a => [a.href, a.current]),
        [[destination, destination === route ? "page" : "location"]], route);
      assert.equal(await page.locator(".site-nav").count(), 1);
      for (const link of links) assert.ok(pages.has(link.href), `unregistered destination: ${link.href}`);
    };
    for (const route of pages.keys()) {
      assert.equal((await page.goto(base + route)).status(), 200, route);
      await checkMenu(route);
      ++report.registeredPages;
    }
    const representatives = ["/help/", "/en/help/", "/", "/en/", "/works/", "/en/works/",
      "/proza/pereborsh/glava-01/", "/en/articles/the-formula-of-god/", "/search/", "/en/search/"];
    const layout = async () => {
      const state = await page.evaluate(() => {
        const nodes = [...document.querySelectorAll(".site-nav a, .languages a")];
        const boxes = nodes.map(node => node.getBoundingClientRect());
        return { overflow: document.documentElement.scrollWidth > innerWidth,
          outside: boxes.some(b => b.left < 0 || b.right > innerWidth || b.height < 44),
          overlaps: boxes.some((a, i) => boxes.slice(i + 1).some(b =>
            Math.min(a.right, b.right) > Math.max(a.left, b.left) + 1 &&
            Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top) + 1)),
          menuRows: new Set([...document.querySelectorAll(".site-nav a")].map(a =>
            Math.round(a.getBoundingClientRect().top))).size };
      });
      assert.equal(state.overflow, false, `overflow: ${page.url()}`);
      assert.equal(state.outside, false, `clipped menu: ${page.url()}`);
      assert.equal(state.overlaps, false, `overlap: ${page.url()}`);
      return state.menuRows;
    };
    for (const width of [320, 375, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of representatives) {
        await page.goto(base + route);
        const rows = await layout();
        await checkMenu(route);
        // Every primary menu anchor is reachable in order using Tab.
        const targets = catalog.navigation.items.map(item => item.targets[pages.get(route).language]);
        for (const target of targets) {
          await page.keyboard.press("Tab");
          assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), target);
          assert.equal(await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle), "solid");
        }
        if (route.endsWith("help/")) {
          const summaries = page.locator("details summary");
          for (let i = 0; i < await summaries.count(); ++i) {
            await summaries.nth(i).focus();
            await page.keyboard.press("Enter");
            assert.equal(await summaries.nth(i).evaluate(node => node.parentElement.open), true);
            await layout();
            await page.keyboard.press("Space");
            assert.equal(await summaries.nth(i).evaluate(node => node.parentElement.open), false);
            ++report.disclosures;
          }
          const other = route === "/help/" ? "/en/help/" : "/help/";
          await page.locator(`.languages a[href="${other}"]`).click();
          assert.equal(new URL(page.url()).pathname, other);
          await checkMenu(other);
          await page.locator(`.languages a[href="${route}"]`).click();
          assert.equal(new URL(page.url()).pathname, route);
          ++report.languageRoundTrips;
          await page.locator(".site-nav a").first().focus();
          await page.keyboard.press("Enter");
          await page.waitForURL(base + targets[0]);
          assert.equal(new URL(page.url()).pathname, targets[0]);
          await page.locator(`.site-nav a[href="${route}"]`).focus();
          await page.keyboard.press("Enter");
          await page.waitForURL(base + route);
          assert.equal(new URL(page.url()).pathname, route);
        }
        if (process.env.HELP_EVIDENCE_DIR) {
          const name = route.replaceAll("/", "_") || "home";
          await page.screenshot({ path: path.join(process.env.HELP_EVIDENCE_DIR, `${name}-${width}.png`), fullPage: true });
        }
        report.layouts.push({ route, width, rows });
      }
    }
    // Menus, reciprocal switches and disclosures also work with JavaScript disabled.
    const noScript = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 320, height: 900 } });
    const plain = await noScript.newPage();
    await plain.goto(base + "/help/");
    await plain.locator("summary").first().click();
    assert.equal(await plain.locator("details").first().getAttribute("open"), "");
    await plain.locator('.languages a[lang="en"]').click();
    assert.equal(new URL(plain.url()).pathname, "/en/help/");
    await plain.locator('.site-nav a[href="/en/works/"]').click();
    assert.equal(new URL(plain.url()).pathname, "/en/works/");
    await noScript.close();
    assert.deepEqual(errors, []);
    if (process.env.HELP_EVIDENCE_DIR) await fs.writeFile(
      path.join(process.env.HELP_EVIDENCE_DIR, "browser-coverage.json"), JSON.stringify(report, null, 2));
    console.log(`PASS: ${report.registeredPages} menus; ${report.layouts.length} responsive layouts; ` +
      `${report.disclosures} keyboard disclosures; ${report.languageRoundTrips} reciprocal language round trips; JS-off navigation.`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
