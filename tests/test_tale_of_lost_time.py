"""Text fidelity and the authored article catalog's 30-to-31 boundary."""

import hashlib
from html import unescape
import json
import re
import unittest
from xml.etree import ElementTree as ET

from tools import generate_publication as generator
from tools.search_index import SearchText


class LostTimeTests(unittest.TestCase):
    def test_complete_supplied_text_and_discovery(self):
        hashes = {
            "ru": "b874139c346c61e9ecfb24345c4cae0f9a6132b4d06b723d32e8c743c5b80226",
            "en": "dd263f441fdadb735741df583197c738b949152f4f89b28418d53552591ad974",
        }
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/tale-of-lost-time/"
            source = (generator.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(len(paragraphs), 4)
            self.assertEqual(hashlib.sha256("\n\n".join(paragraphs).encode()).hexdigest(), hashes[language])
            if language == "ru":
                self.assertIn("бОльшей", paragraphs[0])
                self.assertFalse(paragraphs[0].startswith("\u2003"))
                self.assertTrue(all(p.startswith("\u2003") for p in paragraphs[1:]))
            self.assertIn('href="https://samlib.ru/b/berezina_e_l/rdbyn248cctywbz.shtml">Samlib</a>', source)
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = generator.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(source.count(generator.BEACON_URL), 1)
            index = generator.ROOT / ("assets/search-index.json" if language == "ru" else "assets/search-index-en.json")
            entry = next(p for p in json.loads(index.read_bytes())["pages"] if p["url"] == generator.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text +
                             (" Оригинал на русском: Samlib." if language == "ru" else " Russian original: Samlib."))

    def test_lost_time_order_and_page_four_are_preserved(self):
        catalog, _, groups = generator.prepare(generator.ROOT)
        works = [w["path"] for w in catalog["works"]["items"] if w["type"] == "article"]
        self.assertEqual(len(works), 33)
        self.assertEqual(works[-4:-2], ["/articles/piece-of-cybernetics/", "/articles/tale-of-lost-time/"])
        sitemap = ET.fromstring((generator.ROOT / "sitemap.xml").read_bytes())
        urls = {n.text for n in sitemap.findall("{*}url/{*}loc")}
        for language, base in (("ru", "/articles/"), ("en", "/en/articles/")):
            expected = [groups[p][language] for p in works]
            # The prior 30 entries still occupy exactly the same three pages.
            self.assertEqual([len(expected[:30][i:i+10]) for i in range(0, 30, 10)], [10, 10, 10])
            for number in range(1, 5):
                route = base if number == 1 else base + f"page-{number}/"
                source = (generator.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
                self.assertEqual(re.findall(r'<div class="item">\s*<a href="([^"]+)"', source),
                                 expected[(number-1)*10:number*10])
                if number == 3:
                    self.assertEqual(source.count(f'href="{base}page-4/" rel="next"'), 2)
                if number == 4:
                    self.assertIn(generator.SITE + route, urls)
                    self.assertEqual(source.count(f'href="{base}page-3/" rel="prev"'), 2)
                    self.assertEqual(source.count(generator.BEACON_URL), 1)
                    page = generator.PageHTML(source)
                    metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
                    self.assertTrue(metadata["description"])
                    self.assertEqual(metadata["og:description"], metadata["description"])
                    self.assertEqual(metadata["twitter:description"], metadata["description"])


if __name__ == "__main__":
    unittest.main()
