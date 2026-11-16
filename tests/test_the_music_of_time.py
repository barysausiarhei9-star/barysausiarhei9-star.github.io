"""Article #27: supplied bilingual text and preservation against Article #26."""
from hashlib import sha256
from html import unescape
import json
import re
import subprocess
import unittest
from xml.etree import ElementTree as ET

from tools import generate_publication as g
from tools.search_index import SearchText


BASELINE = "6d675db80d668e948ff9199523d79e60053e66f5"
SLUG = "the-music-of-time"
SOURCE = "https://samlib.ru/b//berezina_e_l/vepsrfdhtvtyb.shtml"


def old(name):
    return subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=g.ROOT)


def is_new(path):
    return path.endswith("/articles/" + SLUG + "/")


class MusicOfTimeTests(unittest.TestCase):
    def test_complete_supplied_paragraphs_and_metadata(self):
        # SHA-256 of each supplied body, joined with its blank paragraph lines.
        hashes = {
            "ru": "6f38034234d348f437fea4f7ef1372b49ba66594a7256f0e932837b9a740ea70",
            "en": "f191a714234ee71c7522fc0561f259ae8bc01c37246f4d9a7b8ca329445534b2",
        }
        titles = {"ru": "МУЗЫКА ВРЕМЕНИ: КРЕЩЕНДО И ДИМИНУЭНДО",
                  "en": "THE MUSIC OF TIME: CRESCENDO AND DIMINUENDO"}
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/" + SLUG + "/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(
                r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(len(paragraphs), 14)
            self.assertEqual(sha256("\n\n".join(paragraphs).encode()).hexdigest(), hashes[language])
            self.assertIn('<h1><strong>' + titles[language] + '</strong></h1>', source)
            listing = (g.ROOT / prefix / 'articles/page-5/index.html').read_text(encoding='utf8')
            card = re.search(r'<a href="' + re.escape(route) + r'">(.*?)</a>', listing, re.S)[1]
            self.assertEqual(unescape(card).strip(), titles[language])
            if language == "ru":
                for phrase in ("бОльшая", "ни что", "СЖАТИЕ", "ОТРИЦАТЕЛЬНЫЙ ПРИРОСТ",
                               "НАПРАВЛЕННОСТИ ДВИЖЕНИЯ"):
                    self.assertIn(phrase, body)
            self.assertIn('href="' + SOURCE + '"', source)
            self.assertIn('class="back" href="/' + prefix + 'articles/page-5/"', source)
            page = g.PageHTML(source)
            meta = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertTrue(meta["description"])
            self.assertEqual(meta["description"], meta["og:description"])
            self.assertEqual(meta["description"], meta["twitter:description"])
            self.assertEqual(meta["og:title"], titles[language])
            self.assertEqual(meta["twitter:title"], titles[language])
            self.assertEqual(meta["og:type"], "article")
            self.assertIn({"rel": "canonical", "href": g.SITE + route}, page.matching("link"))
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/" + SLUG + "/"
                self.assertIn({"rel": "alternate", "hreflang": lang, "href": g.SITE + target}, page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == lang]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == language else None)
            data = json.loads("".join(page.scripts[0]))
            self.assertEqual((data["@type"], data["headline"], data["url"], data["inLanguage"]),
                             ("Article", titles[language], g.SITE + route, language))
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"] if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText(source).text)
            for slug in ("twins-without-a-paradox", "negative-time", "time-zones-of-the-universe", "the-path-of-progress"):
                previous = (g.ROOT / prefix / "articles" / slug / "index.html").read_text(encoding="utf8")
                self.assertNotIn(titles[language], previous)
                self.assertNotIn(paragraphs[0], previous)
                self.assertNotIn(SOURCE, previous)

    def test_prior_catalog_authored_pages_and_discovery_records_preserved(self):
        previous = json.loads(old("publication/catalog.json"))
        current = g.load_json(g.ROOT / "publication/catalog.json")
        pairs = g.article_pairs(current)
        self.assertEqual(len(pairs), 44)
        for lang in ("ru", "en"):
            self.assertEqual([p[lang]["path"] for p in pairs[:-1]],
                             [p[lang]["path"] for p in g.article_pairs(previous)])
            self.assertTrue(pairs[-2][lang]["path"].endswith("/on-all-kinds-of-mysteries/"))
            counts = []
            for number in range(1, 6):
                name = g.article_route(lang, number).lstrip("/") + "index.html"
                source = (g.ROOT / name).read_bytes()
                counts.append(source.count(b'<div class="item">'))
                if number < 5:
                    self.assertEqual(source, old(name), name)
            self.assertEqual(counts, [10, 10, 10, 10, 4])
        for key, field in (("pages", "path"), ("alternate_groups", "ru")):
            current[key] = [p for p in current[key] if not is_new(p[field])]
        current["works"]["items"] = [p for p in current["works"]["items"] if not is_new(p["path"])]
        self.assertEqual(current, previous)
        for p in previous["pages"]:
            if g.is_article_listing(p["path"]) or p["path"] in ("/works/", "/en/works/"):
                continue
            name = p["path"].lstrip("/") + "index.html"
            self.assertEqual((g.ROOT / name).read_text(encoding="utf8"),
                             old(name).decode().replace("\r\n", "\n"), name)
        for name, key in (("api/agent-feed/v1.json", "entries"), ("assets/search-index.json", "pages"),
                          ("assets/search-index-en.json", "pages")):
            data = json.loads((g.ROOT / name).read_bytes())
            data[key] = [p for p in data[key] if not is_new(p.get("url", p.get("id", "")))]
            self.assertEqual(data, json.loads(old(name)), name)
        def semantics(node):
            return (node.tag, sorted(node.attrib.items()), (node.text or "").strip(),
                    [semantics(child) for child in node])
        for name in ("sitemap.xml", "feed.xml"):
            tree = ET.fromstring((g.ROOT / name).read_bytes())
            parent = tree.find("channel") if name == "feed.xml" else tree
            for node in list(parent):
                if is_new(node.findtext("link") or node.findtext("{*}loc") or ""):
                    parent.remove(node)
            self.assertEqual(semantics(tree), semantics(ET.fromstring(old(name))), name)
        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        for name, expected in g.render_article_pages(g.ROOT, g.article_catalog(catalog)).items():
            self.assertEqual((g.ROOT / name).read_bytes(), expected, name)


if __name__ == "__main__":
    unittest.main()
