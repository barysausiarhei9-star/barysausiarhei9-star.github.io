/* Local-only UI checks. Uses an installed Playwright; no production requests. */
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const mime = { ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png" };

async function main() {
  const server = http.createServer(async (request, response) => {
    try {
      let relative = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
      if (relative.endsWith("/")) relative += "index.html";
      const target = path.resolve(root, "." + relative);
      if (!target.startsWith(root + path.sep)) throw new Error("Outside root");
      const bytes = await fs.readFile(target);
      response.writeHead(200, { "Content-Type": mime[path.extname(target)] || "application/octet-stream" });
      response.end(bytes);
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ headless: true });
    const errors = [];
    for (const width of [1280, 768, 375, 320]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      // Canonical result links stay clickable while all requests stay local.
      await context.route("https://schrodingercat.org/**", async route => {
        const remote = new URL(route.request().url());
        await route.fulfill({ response: await context.request.get(base + remote.pathname + remote.search) });
      });
      const page = await context.newPage();
      page.on("pageerror", error => errors.push(error.message));
      let loads = 0;
      page.on("request", request => { if (request.url().endsWith("/assets/search-index.json")) ++loads; });
      await page.goto(base + "/search/");
      const status = page.locator("#search-status");
      const input = page.getByLabel("Что найти?");
      const noOverflow = async () => assert.equal(await page.evaluate(() =>
        document.documentElement.scrollWidth <= window.innerWidth), true, `overflow at ${width}`);
      assert.match(await status.textContent(), /Введите/);
      await noOverflow();
      assert.equal(loads, 0);
      const navigation = page.locator('.site-nav a[href="/search/"]');
      assert.equal(await navigation.isVisible(), true);
      assert.ok((await navigation.boundingBox()).height >= 44);
      await input.fill("ФОРМУЛА БОГА");
      await page.getByRole("button", { name: "Найти", exact: true }).click();
      await page.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Найдено:"));
      const first = page.locator("#search-results a").first();
      assert.equal(await first.getAttribute("href"), "https://schrodingercat.org/articles/formula-boga/");
      await noOverflow();
      if (width === 1280 || width === 375) {
        await page.screenshot({ path: path.join(os.tmpdir(), `schrodinger-search-${width}.png`), fullPage: true });
      }
      await input.fill('"жил да был один король"');
      await page.waitForFunction(() => document.querySelector("#search-status").textContent === "Найдено: 1");
      assert.equal(await page.locator("#search-results a").first().getAttribute("href"),
        "https://schrodingercat.org/poeziya/a-koronu/");
      await input.fill("невозможныйзапрос");
      await page.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Ничего"));
      assert.equal(await page.locator("#search-results li").count(), 0);
      await input.fill("");
      await page.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Введите"));
      assert.equal(loads, 1, "index reused across queries");
      await page.goto(base + "/search/?q=" + encodeURIComponent("двоичн"));
      await page.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Найдено:"));
      await page.locator('#search-results a[href="https://schrodingercat.org/articles/formula-boga/"]').click();
      await page.waitForURL("https://schrodingercat.org/articles/formula-boga/");
      assert.equal(await page.locator("h1").textContent(), "Формула бога");
      await page.locator('.site-nav a[href="/search/"]').click();
      await page.waitForURL("https://schrodingercat.org/search/");
      await context.close();
      console.log(`PASS: ${width}px layout, search, empty state, canonical links and navigation`);
    }
    const context = await browser.newContext();
    const page = await context.newPage();
    const payload = '<img src=x onerror="window.searchXSS=true"> & <script>window.searchXSS=true</script>';
    await page.route("**/assets/search-index.json", route => route.fulfill({
      contentType: "application/json", body: JSON.stringify({ pages: [{
        url: "https://schrodingercat.org/about/", title: payload, text: payload
      }] })
    }));
    await page.goto(base + "/search/?q=img");
    await page.waitForFunction(() => document.querySelector("#search-status").textContent === "Найдено: 1");
    assert.equal(await page.locator("#search-results a").textContent(), payload);
    assert.equal(await page.locator("#search-results p").textContent(), payload);
    assert.equal(await page.locator("#search-results img, #search-results script").count(), 0);
    assert.equal(await page.evaluate(() => window.searchXSS), undefined);
    await context.close();

    const failure = await browser.newContext();
    const failurePage = await failure.newPage();
    await failurePage.route("**/assets/search-index.json", route => route.fulfill({ status: 503, body: "unavailable" }));
    await failurePage.goto(base + "/search/?q=кошка");
    await failurePage.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Не удалось"));
    await failurePage.unroute("**/assets/search-index.json");
    await failurePage.getByRole("button", { name: "Найти", exact: true }).click();
    await failurePage.waitForFunction(() => document.querySelector("#search-status").textContent.startsWith("Найдено:"));
    await failure.close();
    assert.deepEqual(errors, []);
    console.log("PASS: browser HTML escaping, fetch failure/retry, no JavaScript errors");
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
