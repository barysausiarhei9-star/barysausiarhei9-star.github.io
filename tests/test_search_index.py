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

    def test_preface_is_searchable_with_visible_ampersand_in_both_languages(self):
        for language in ("ru", "en"):
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            prefix = "/en" if language == "en" else ""
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/preface-to-a-non-bestseller/")
            self.assertTrue(page["text"].startswith("& "))
            self.assertNotIn("&amp;", page["text"])
            self.assertIn("бесцеллеру" if language == "ru" else "NON-BESTSELLER", page["title"])
            self.assertIn("ад инфинито." if language == "ru" else "ad infinitum.", page["text"])

    def test_hint_is_searchable_in_both_languages(self):
        for language, prefix, title, first, last in (
                ("ru", "", "Подсказка", "Если фотон от солнца в пути 7 минут", "должно характеризоваться его снижением."),
                ("en", "/en", "A HINT", "If a photon from the Sun has been traveling for 7 minutes", "a decrease in that magnitude."),
        ):
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/a-hint/")
            self.assertIn(title, page["title"])
            self.assertTrue(page["text"].startswith(first))
            self.assertIn(last, page["text"])

    def test_dissection_is_searchable_in_both_languages(self):
        for language, prefix, title, first, last in (
                ("ru", "", 'ПРЕПАРАЦИЯ ТЕОРИИ ОТНОСИТЕЛЬНОСТИ', "Принцип относительности времени", "при скорости света."),
                ("en", "/en", 'DISSECTION OF THE THEORY OF RELATIVITY', "The principle of the relativity of time", "at the speed of light."),
        ):
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/dissection-of-the-theory-of-relativity/")
            self.assertIn(title, page["title"])
            self.assertTrue(page["text"].startswith(first))
            self.assertIn(last, page["text"])

    def test_meow_complete_text_is_searchable_in_both_languages(self):
        for language, prefix, first, last in (
                ("ru", "", "Свое дело я выполнила", "На этом, пожалуй, остановлюсь."),
                ("en", "/en", "I have done my part", "I think I shall stop here.")):
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/meow/")
            self.assertIn("Meow", page["title"])
            self.assertTrue(page["text"].startswith(first))
            self.assertIn(last, page["text"])
            self.assertIn("mc2 + (i2)mc2", page["text"])
            self.assertIn("12.", page["text"])
            self.assertIn("13.", page["text"])
            self.assertNotIn("11.", page["text"])

    def test_piece_of_cybernetics_complete_text_is_searchable_in_both_languages(self):
        for language, prefix in (("ru", ""), ("en", "/en")):
            source = (generator.ROOT / prefix.lstrip("/") / "articles/piece-of-cybernetics/index.html").read_text(encoding="utf-8")
            body = source.split('<div id="article-text">', 1)[1].split('</div>', 1)[0]
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/piece-of-cybernetics/")
            self.assertEqual(page["text"], SearchText("<main>" + body + "</main>").text + (" Оригинал на русском: Samlib." if language == "ru" else " Russian original: Samlib."))
            self.assertTrue(page["text"].startswith("... "))
            self.assertIn("Р.Эшби" if language == "ru" else "R. Ashby", page["text"])
            self.assertIn("для любого из перечисленных объектов." if language == "ru" else "in any of those places.", page["text"])

    def test_eto_zh_nado_is_searchable_in_both_languages(self):
        for language, prefix, title, first, last in (
                ("ru", "", "Это ж надо!", "В космосе единственные", "вне зависимости от вашего на этот счет мнения."),
                ("en", "/en", "Well, Would You Look at That!", "In the cosmos", "regardless of what you may think about it.")):
            pages = json.loads(render_search(generator.ROOT, self.catalog, language))["pages"]
            page = next(p for p in pages if p["url"] == generator.SITE + prefix + "/articles/eto-zh-nado/")
            self.assertIn(title, page["title"])
            self.assertTrue(page["text"].startswith(first))
            self.assertIn(last, page["text"])

    def test_inventory_and_no_duplicate_bodies(self):
        by_url = {p["url"]: p for p in self.pages}
        self.assertEqual(len(by_url), 92)
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
        self.assertEqual(len(english), 38)  # Includes reader help, the companion atlas and all article translations.
        self.assertEqual({p["language"] for p in self.pages}, {"ru"})
        self.assertTrue(english.isdisjoint(p["url"] for p in self.pages))

    def test_english_inventory_language_isolation_and_determinism(self):
        data = render_search(generator.ROOT, self.catalog, "en")
        pages = json.loads(data)["pages"]
        expected = {generator.SITE + p["path"] for p in self.catalog["pages"]
                    if p["language"] == "en" and p["page_type"] == "content"}
        self.assertEqual(len(pages), 38)
        self.assertEqual({p["url"] for p in pages}, expected)
        self.assertEqual({p["language"] for p in pages}, {"en"})
        self.assertTrue(all(p["text"] for p in pages))
        self.assertTrue(expected.isdisjoint(p["url"] for p in self.pages))
        shuffled = dict(self.catalog, pages=list(reversed(self.catalog["pages"])))
        self.assertEqual(data, render_search(generator.ROOT, shuffled, "en"))
        self.assertEqual(data, (generator.ROOT / "assets/search-index-en.json").read_bytes())
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", data)

    def test_search_routes_publication_and_rss(self):
        outputs = generator.render()
        from xml.etree import ElementTree as ET
        rss_links = {item.findtext("link") for item in ET.fromstring(outputs["feed.xml"]).findall("channel/item")}
        feed = json.loads(outputs["api/agent-feed/v1.json"])
        for path in ("/search/", "/en/search/"):
            url = generator.SITE + path
            self.assertNotIn(url, rss_links)
            self.assertIn(url.encode(), outputs["sitemap.xml"])
            entry = next(e for e in feed["entries"] if e["canonical_url"] == url)
            self.assertEqual(entry["page_type"], "section_index")

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
            else:
                nav = [a for a in html.matching("a") if a.get("href") == "/en/search/"]
                self.assertEqual(len(nav), 2 if page["path"] == "/en/search/" else 1)
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
