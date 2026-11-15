"""Article #22: complete Samlib text, aligned translation and prior-publication preservation."""
from hashlib import sha256
from html import unescape
import json
import re
import subprocess
import unittest
from xml.etree import ElementTree as ET

from tools import generate_publication as g
from tools.search_index import SearchText


SOURCE = "https://samlib.ru/b/berezina_e_l/genmghjuhtccf.shtml"
SLUG = "the-path-of-progress"
BASELINE = "4cbedf380b6ec0de397522f0b6d7941d245cb9e2"
FIXTURES = g.ROOT / "tests/fixtures"


class PathOfProgressTests(unittest.TestCase):
    def test_complete_source_and_aligned_translation(self):
        # Captured from HTTP 200, windows-1251, at SOURCE on 2026-11-15.
        # JSON strings preserve literal source spaces without trailing file whitespace.
        fragment = (FIXTURES / (SLUG + "-samlib.json")).read_text(encoding="utf8")
        self.assertEqual(sha256(fragment.encode()).hexdigest(),
                         "950698d13b5c67dc63bd983f81018070032370e9af07489d0e663c8c19a16d05")
        ru = [unescape(line[4:]) for line in json.loads(fragment)]
        english = (FIXTURES / (SLUG + "-en.json")).read_text(encoding="utf8")
        self.assertEqual(sha256(english.encode()).hexdigest(),
                         "e37fd114afabc21d019bf0614afc30e38ece989a6740b4b101dd25eb4b505ae2")
        en = json.loads(english)
        self.assertEqual(len(ru), 63)
        self.assertEqual(len(en), len(ru))
        self.assertEqual(sum(bool(p.strip()) for p in ru), 54)
        self.assertEqual([bool(p.strip()) for p in en], [bool(p.strip()) for p in ru])
        self.assertEqual(ru[0], "\u2003ПУТЬ ПРОГРЕССА")
        self.assertEqual(ru[-1], '\u2003Ибо основная мысль Эйнштейна: "Перрончик тронется - вагон останется"! ')
        for phrase in ("Вобщем", "бОльшая", "бОльшей", "СВОЕГО СОБСТВЕННОГО", "С ТОЧКИ ЗРЕНИЯ ДРУГ ДРУГА", "ОТРИЦАТЕЛЬНЫЙ ПРИРОСТ", "НАПРАВЛЕННОСТИ  ДВИЖЕНИЯ ПРОЧЬ ОТ НАБЛЮДАТЕЛЯ"):
            self.assertIn(phrase, "\n".join(ru))
        for phrase in ("twin paradox", "ONE’S OWN", "FROM EACH OTHER’S POINT OF VIEW", "NEGATIVE INCREMENT", "DIRECTION OF MOVEMENT AWAY FROM THE OBSERVER", "magnitude of velocity", "vector of movement", "INCREASE FASTER", "DECREASE FASTER", "The little platform will move off—the carriage will stay behind"):
            self.assertIn(phrase, "\n".join(en))
        for lang, prefix, expected, title in (("ru", "", ru, "Путь прогресса"), ("en", "en/", en, "The Path of Progress")):
            route = "/" + prefix + "articles/" + SLUG + "/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            actual = [unescape(p) for p in re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(actual, expected)
            self.assertIn('<h1><strong>' + title + '</strong></h1>', source)
            label = "Оригинал на русском: " if lang == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), ['<div class="note">' + label + '<a href="' + SOURCE + '">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            meta = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertEqual(meta["og:title"], title)
            self.assertEqual(meta["twitter:title"], title)
            self.assertEqual(meta["description"], meta["og:description"])
            self.assertEqual(meta["description"], meta["twitter:description"])
            self.assertEqual(meta["og:type"], "article")
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for other, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/" + SLUG + "/"
                self.assertIn({"rel": "alternate", "hreflang": other, "href": g.SITE + target}, page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == other]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == other else None)
            index = "assets/search-index" + ("-en" if lang == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"] if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText(source).text)
            if lang == "en":
                self.assertIn("The arguments and quotations below are presented as the author’s, rather than as statements of established physics.", source)

    def test_prior_pages_catalog_and_discovery_records_are_unchanged(self):
        def old(name):
            return subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith("/articles/" + SLUG + "/")

        previous = json.loads(old("publication/catalog.json"))
        current = g.load_json(g.ROOT / "publication/catalog.json")
        articles = [w["path"] for w in current["works"]["items"] if w["type"] == "article"]
        self.assertEqual(len(articles), 39)
        self.assertEqual(articles[-2:], ["/articles/in-another-dimension/", "/articles/" + SLUG + "/"])
        for key, field in (("pages", "path"), ("alternate_groups", "ru")):
            current[key] = [p for p in current[key] if not is_new(p[field])]
        current["works"]["items"] = [p for p in current["works"]["items"] if not is_new(p["path"])]
        self.assertEqual(current, previous)
        for p in previous["pages"]:
            if g.is_article_listing(p["path"]) or p["path"] in ("/works/", "/en/works/"):
                continue
            name = p["path"].lstrip("/") + "index.html"
            self.assertEqual((g.ROOT / name).read_text(encoding="utf8"), old(name).decode().replace("\r\n", "\n"), name)
        for name, key in (("api/agent-feed/v1.json", "entries"), ("assets/search-index.json", "pages"), ("assets/search-index-en.json", "pages")):
            data = json.loads((g.ROOT / name).read_bytes())
            data[key] = [p for p in data[key] if not is_new(p.get("url", p.get("id", "")))]
            self.assertEqual(data, json.loads(old(name)), name)
        for name in ("sitemap.xml", "feed.xml"):
            tree = ET.fromstring((g.ROOT / name).read_bytes())
            parent = tree.find("channel") if name == "feed.xml" else tree
            for node in list(parent):
                url = node.findtext("link") or node.findtext("{*}loc") or ""
                if is_new(url):
                    parent.remove(node)
            def semantics(node):
                return (node.tag, sorted(node.attrib.items()), (node.text or "").strip(),
                        [semantics(child) for child in node])
            self.assertEqual(semantics(tree), semantics(ET.fromstring(old(name))), name)
        for prefix in ("", "en/"):
            counts = []
            for number in range(1, 5):
                name = prefix + "articles/" + (f"page-{number}/" if number > 1 else "") + "index.html"
                source = (g.ROOT / name).read_text(encoding="utf8")
                counts.append(source.count('<div class="item">'))
                if number == 4:
                    source = re.sub(r'\n        <div class="item">\n          <a href="/' + prefix + r'articles/the-path-of-progress/">.*?</div>\n', "", source, flags=re.S)
                self.assertEqual(source, old(name).decode(), name)
            self.assertEqual(counts, [10, 10, 10, 9])


if __name__ == "__main__":
    unittest.main()
