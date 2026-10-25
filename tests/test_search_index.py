"""Focused extraction, route, coverage and byte determinism checks."""

import json
from pathlib import Path
import tempfile
import unittest

from tools import generate_publication as generator
from tools.search_index import SearchText, render_search


class SearchIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, _, _ = generator.prepare(generator.ROOT)
        cls.data = render_search(generator.ROOT, cls.catalog)
        cls.pages = json.loads(cls.data)["pages"]

    def test_text_boundaries_entities_and_exclusions(self):
        source = '''<html><head><title>metadata</title></head><body>
        <header>header</header><main><h1>Title</h1><nav>navigation</nav>
        <p>Кошка <em>Шрёдингера</em> &amp; &lt;текст&gt;</p><p>Следующий<br/>абзац</p>
        <script>script</script><style>style</style><template>template</template>
        <noscript>fallback</noscript><footer>footer</footer>
        <a class="back" href="/">back</a><p class="book-author">author</p>
        <p hidden>hidden</p><div aria-hidden="true">invisible</div>
        <figure><img alt="not OCR"/><figcaption>caption</figcaption></figure>
        <form><label>controls</label><button>button</button></form></main></body></html>'''
        self.assertEqual(SearchText(source).text,
                         'Кошка Шрёдингера & <текст> Следующий абзац')

    def test_inventory_and_no_duplicate_bodies(self):
        by_url = {p["url"]: p for p in self.pages}
        self.assertEqual(len(by_url), 65)
        catalog = {generator.SITE + p["path"]: p for p in self.catalog["pages"]}
        for url, page in by_url.items():
            with self.subTest(url=url):
                self.assertEqual(catalog[url]["page_type"], "content")
                self.assertEqual(page["title"], catalog[url]["title"])
                self.assertEqual(page["language"], catalog[url]["language"])
                self.assertTrue((generator.ROOT / (url.removeprefix(generator.SITE + "/") + "index.html")).is_file())
                self.assertNotIn("←", page["text"])
        bodies = [(p["language"], p["text"].casefold()) for p in self.pages if p["text"]]
        self.assertEqual(len(bodies), len(set(bodies)))
        self.assertIn(generator.SITE + "/about/", by_url)
        self.assertIn(generator.SITE + "/articles/about/", by_url)
        self.assertNotEqual(by_url[generator.SITE + "/about/"]["text"],
                            by_url[generator.SITE + "/articles/about/"]["text"])
        self.assertNotIn(generator.SITE + "/search/", by_url)
        for number in range(1, 28):
            self.assertTrue(by_url[generator.SITE + f"/proza/pereborsh/glava-{number:02}/"]["text"])
        for page in self.catalog["pages"]:
            if page["text_availability"] == "image_only":
                self.assertEqual(by_url[generator.SITE + page["path"]]["text"], "")

    def test_published_english_content_is_excluded(self):
        english = {generator.SITE + p["path"] for p in self.catalog["pages"]
                   if p["language"] == "en" and p["page_type"] == "content"}
        self.assertEqual(len(english), 11)  # Exercise existing published English content.
        self.assertEqual({p["language"] for p in self.pages}, {"ru"})
        self.assertTrue(english.isdisjoint(p["url"] for p in self.pages))

    def test_duplicate_bodies_and_noncontent_pages_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("original", "replica"):
                target = root / name / "index.html"
                target.parent.mkdir()
                target.write_text('<main><p>Один и тот же текст.</p></main>', encoding="utf-8")
            pages = [{"path": f"/{name}/", "title": name, "language": "ru",
                      "page_type": kind, "text_availability": "html_text"}
                     for name, kind in (("original", "content"), ("replica", "content"),
                                        ("listing", "section_index"), ("future", "placeholder"))]
            data = json.loads(render_search(root, {"site_url": generator.SITE, "pages": pages}))
            self.assertEqual([p["url"] for p in data["pages"]], [generator.SITE + "/original/"])

    def test_deterministic_bytes_and_checked_in_output(self):
        self.assertEqual(self.data, render_search(generator.ROOT, self.catalog))
        shuffled = dict(self.catalog, pages=list(reversed(self.catalog["pages"])))
        self.assertEqual(self.data, render_search(generator.ROOT, shuffled))
        self.assertEqual(self.data, (generator.ROOT / "assets/search-index.json").read_bytes())
        self.assertFalse(self.data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", self.data)

    def test_russian_navigation_and_local_links(self):
        for page in self.catalog["pages"]:
            html = generator.validate_html(generator.ROOT, page)
            if page["language"] == "ru":
                self.assertEqual(sum(a.get("href") == "/search/" for a in html.matching("a")),
                                 2 if page["path"] == "/search/" else 1)
            for tag in ("a", "link", "script", "img"):
                for attrs in html.matching(tag):
                    href = attrs.get("href", attrs.get("src", ""))
                    if not href.startswith("/") or href.startswith("//"):
                        continue
                    path = href.split("#")[0].split("?")[0]
                    target = generator.ROOT / path.lstrip("/")
                    self.assertTrue((target / "index.html").is_file() if path.endswith("/")
                                    else target.is_file(), (page["path"], href))


if __name__ == "__main__":
    unittest.main()
