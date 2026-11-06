/* Run with an installed Playwright (NODE_PATH supported). Local requests only.
   Compare against HEAD to verify the analytics change has no visible effect. */
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const beacon = "https://static.cloudflareinsights.com/beacon.min.js";
const token = "6c1d21ba580d43d59bf01f1b9c440f4f";
const mime = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
  ".json": "application/json", ".png": "image/png" };

async function main() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost");
      let name = decodeURIComponent(url.pathname).replace(/^\//, "");
      if (!name || name.endsWith("/")) name += "index.html";
      const target = path.resolve(root, name);
      assert.ok(target.startsWith(root + path.sep));
      const bytes = url.searchParams.has("baseline") && name.endsWith(".html")
        ? execFileSync("git", ["show", `HEAD:${name}`], { cwd: root }) : await fs.readFile(target);
      response.writeHead(200, { "Content-Type": mime[path.extname(name)] || "application/octet-stream" });
      response.end(bytes);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const base = `http://127.0.0.1:${server.address().port}`;
    const context = await browser.newContext();
    // Stub external code so validation cannot send analytics or other external requests.
    await context.route("**/*", route => {
      if (route.request().url() === beacon) return route.fulfill({ contentType: "text/javascript", body: "" });
      return new URL(route.request().url()).origin === base ? route.continue() : route.abort();
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let requests = 0;
    page.on("request", request => { if (request.url() === beacon) ++requests; });
    const routes = ["/", "/en/", "/articles/", "/en/articles/the-formula-of-god/",
      "/works/", "/en/works/", "/kniga/", "/en/book/", "/proza/pereborsh/glava-01/",
      "/poeziya/white-thread/", "/help/", "/en/help/", "/search/", "/en/search/"];
    let comparisons = 0;
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of routes) {
        const screenshots = [];
        for (const baseline of [true, false]) {
          const before = requests;
          assert.equal((await page.goto(base + route + (baseline ? "?baseline=1" : ""))).status(), 200);
          await page.evaluate(() => document.fonts.ready);
          await page.evaluate(() => Promise.all([...document.images].map(image => {
            image.loading = "eager";
            return image.decode().catch(() => {});
          })));
          const scripts = page.locator(`script[src="${beacon}"]`);
          assert.equal(await scripts.count(), baseline ? 0 : 1);
          assert.equal(requests - before, baseline ? 0 : 1);
          if (!baseline) {
            assert.equal(await scripts.getAttribute("type"), "module");
            assert.deepEqual(JSON.parse(await scripts.getAttribute("data-cf-beacon")), { token });
          }
          // Warm the full-page raster before comparing decoded, scaled images.
          await page.screenshot({ fullPage: true, animations: "disabled" });
          screenshots.push(await page.screenshot({ fullPage: true, animations: "disabled",
            style: "*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }" }));
        }
        if (!screenshots[1].equals(screenshots[0])) {
          await fs.writeFile(path.join(os.tmpdir(), "analytics-before.png"), screenshots[0]);
          await fs.writeFile(path.join(os.tmpdir(), "analytics-after.png"), screenshots[1]);
        }
        assert.ok(screenshots[1].equals(screenshots[0]), `visible change: ${width}px ${route}`);
        ++comparisons;
      }
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(await context.cookies(), []);
    console.log(`PASS: ${comparisons} Chromium comparisons at 375/1280px; identical screenshots, one beacon request/page, no page errors or cookies (external beacon stubbed).`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
