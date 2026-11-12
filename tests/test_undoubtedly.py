"""Article #18: supplied paragraph fidelity and preservation of prior publications."""
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


class UndoubtedlyTests(unittest.TestCase):
    def test_supplied_paragraphs_and_public_attribution(self):
        expected = {
            "ru": [
                "Что масса частицы зависит от её скорости, ни для кого не секрет.",
                " Отвечая на вопрос Ли Смолина, имеется ли единая фундаментальная сущность, утверждаю: несомненно.",
                " Имеется некая сущность, которая в зависимости от обстоятельств проявляет себя в трех возможных модусах-\"ипостасях\":",
                "  - при досветовой скорости это материальная частица(структура) с обычной положительной массой,",
                "  - при достижении скорости света(или приближении к ней) - это волна, безмассовая энергонесущая частица, \"сгусток энергии\",",
                "  - при скорости, превосходящей световую - это античастица, образование, обладающее при определенных условиях мнимой массой, квадрат которой в некий момент обеспечит массу отрицательную, необходимую для аннигиляции с собственной своей копией-антиподом в материальном выражении.",
                " Следует подчеркнуть, что антивещество живет в \"спт-симметричном\" мире, которому свойственно, прежде всего, отрицательное время."
            ],
            "en": [
                "That the mass of a particle depends on its velocity is no secret to anyone.",
                " In response to Lee Smolin's question of whether there is a single fundamental entity, I assert: undoubtedly.",
                " There is a certain entity which, depending on the circumstances, manifests itself in three possible modes—“hypostases”:",
                "  - at subluminal velocity, it is a material particle (structure) with ordinary positive mass,",
                "  - upon reaching the speed of light (or approaching it), it is a wave, a massless energy-carrying particle, a “bundle of energy”,",
                "  - at a velocity exceeding the speed of light, it is an antiparticle, an entity possessing, under certain conditions, an imaginary mass, the square of which will at some point yield the negative mass necessary for annihilation with its own counterpart-antipode in material form.",
                " It should be emphasized that antimatter exists in a “CPT-symmetric” world characterized, above all, by negative time."
            ]
        }
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/undoubtedly/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(
                r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(paragraphs, expected[language])
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label +
                '<a href="https://samlib.ru/b/berezina_e_l/ytcjvytyyj.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content")
                        for a in page.matching("meta")}
            title = "Несомненно" if language == "ru" else "Undoubtedly"
            self.assertEqual(metadata["og:title"], title)
            self.assertEqual(metadata["twitter:title"], title)
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(metadata["og:type"], "article")
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/undoubtedly/"
                self.assertIn({"rel": "alternate", "hreflang": lang, "href": g.SITE + target},
                              page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == lang]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == language else None)
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"]
                         if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text +
                             " " + label + "Samlib.")

    def test_previous_publications_and_records_are_unchanged(self):
        baseline = "b3dbe2ace1a0ae45cee6f572cb11b7135ea1f71c"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith("/articles/undoubtedly/")

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
                            r'articles/undoubtedly/">.*?</div>\n', "", source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)


if __name__ == "__main__":
    unittest.main()
