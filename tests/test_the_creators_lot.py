"""Article #19: exact supplied text, emphasis, discovery and preservation."""
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


class CreatorsLotTests(unittest.TestCase):
    def test_exact_supplied_text_emphasis_metadata_and_links(self):
        expected = {
            "ru": [
                "ЖРЕБИЙ КРИЭЙТОРА",
                "(теория систем обязывает)",
                '''1. Создатель системы "ВСЕ СУЩЕЕ" не может находиться ВНЕ системы, так как если он не входит в систему , определяемую как "Все Существующее", то он просто-напросто НЕ СУЩЕCТВУЕТ.
2. Он не может и входить в систему "ВСЕ СУЩЕЕ" как ее часть, наряду со своим творением, потому что часть всегда проще целого, а создатель не может быть проще созданной им системы.
3. Остается единственный выход: отождествить Творца с Творением:''',
                "СОЗДАТЕЛЬ ЕСТЬ ВСЕ СУЩЕЕ.",
            ],
            "en": [
                "THE CREATOR’S LOT",
                "(as systems theory requires)",
                '''1. The creator of the system "ALL THAT EXISTS" cannot be OUTSIDE the system, because if he is not part of the system defined as "All That Exists", then he simply DOES NOT EXIST.
2. Nor can he be part of the system "ALL THAT EXISTS" alongside his own creation, because a part is always simpler than the whole, and the creator cannot be simpler than the system he has created.
3. Only one way remains: to identify the Creator with the Creation:''',
                "THE CREATOR IS ALL THAT EXISTS.",
            ],
        }
        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        articles = [w["path"] for w in catalog["works"]["items"] if w["type"] == "article"]
        self.assertEqual(articles[-4:-2], ["/articles/undoubtedly/", "/articles/the-creators-lot/"])
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/the-creators-lot/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            title, subtitle, numbered, final = expected[language]
            self.assertIn("<h1><strong>" + title + "</strong></h1>", source)
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)
            # Strip markup only: never normalize the supplied whitespace or Unicode.
            self.assertEqual([unescape(re.sub(r'<[^>]+>', '', p)) for p in paragraphs],
                             [subtitle, numbered, final])
            self.assertEqual(paragraphs[0], "<strong><em>" + subtitle + "</em></strong>")
            self.assertEqual(paragraphs[-1], "<strong>" + final + "</strong>")
            phrases = (["ВСЕ СУЩЕЕ", "ВНЕ", "НЕ СУЩЕCТВУЕТ", "ВСЕ СУЩЕЕ"] if language == "ru"
                       else ["ALL THAT EXISTS", "OUTSIDE", "DOES NOT EXIST", "ALL THAT EXISTS"])
            self.assertEqual(re.findall(r'<strong>(.*?)</strong>', paragraphs[1]), phrases)
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label +
                '<a href="https://samlib.ru/b/berezina_e_l/230htbq.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertEqual(metadata["og:title"], title)
            self.assertEqual(metadata["twitter:title"], title)
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(metadata["og:type"], "article")
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/the-creators-lot/"
                self.assertIn({"rel": "alternate", "hreflang": lang, "href": g.SITE + target}, page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == lang]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == language else None)
            for attrs in page.matching("a") + page.matching("link"):
                href = attrs.get("href", "")
                if href.startswith("/"):
                    target = g.ROOT / href.lstrip("/")
                    self.assertTrue((target / "index.html").is_file() if href.endswith("/") else target.is_file(), href)
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"] if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text + " " + label + "Samlib.")

    def test_previous_publications_and_records_are_unchanged(self):
        baseline = "ca076ebcd26757143c00b4e90be257cfd3c2b286"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith(("/articles/the-creators-lot/", "/articles/epatazhka/", "/articles/in-another-dimension/"))

        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        previous = json.loads(old("publication/catalog.json"))
        for key, field in (("pages", "path"), ("alternate_groups", "ru")):
            catalog[key] = [p for p in catalog[key] if not is_new(p[field])]
        catalog["works"]["items"] = [w for w in catalog["works"]["items"] if not is_new(w["path"])]
        self.assertEqual(catalog, previous)
        authored = [p["path"].lstrip("/") + "index.html" for p in previous["pages"]
                    if not g.is_article_listing(p["path"]) and p["path"] not in ("/works/", "/en/works/")]
        self.assertEqual(subprocess.check_output(["git", "diff", baseline, "--", *authored], cwd=g.ROOT), b"")
        for name, key in (("api/agent-feed/v1.json", "entries"), ("assets/search-index.json", "pages"),
                          ("assets/search-index-en.json", "pages")):
            current = json.loads((g.ROOT / name).read_bytes())
            current[key] = [p for p in current[key] if not is_new(p.get("url", p.get("id", "")))]
            self.assertEqual(current, json.loads(old(name)), name)
        for prefix in ("", "en/"):
            name = prefix + "articles/page-4/index.html"
            source = (g.ROOT / name).read_text(encoding="utf-8")
            source = re.sub(r'\n        <div class="item">\n          <a href="/' + prefix +
                            r'articles/(?:the-creators-lot|epatazhka|in-another-dimension)/">.*?</div>\n', "", source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)


if __name__ == "__main__":
    unittest.main()
