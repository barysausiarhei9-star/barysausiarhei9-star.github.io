"""Article #17: supplied paragraph fidelity and preservation of prior publications."""
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


class TimeZonesTests(unittest.TestCase):
    def test_supplied_paragraphs_and_public_attribution(self):
        expected = {
            'ru': [
                'Космическое время определяется расстоянием, которое за это время проходит свет.',
                '\u2003Т.е. чем большее расстояние преодолено фотонами, тем больше времени протекло.',
                '\u2003 Мы видим свет позже, чем случился выброс фотонов. Тем позже, чем дальше от нас этот выброс произошел. Вывод: все “события” находятся в другом времени, прошлом по отношению к собственному времени наблюдателя. То есть, в соответствии со степенью удаленности “событий” от наблюдателя, в зависимости от условного значения временных координат места его нахождения, наблюдается снижение модуля обозначающих время положительных величин или же нарастание модуля отрицательных значений времени наблюдаемого “события”. Причем принцип касается любого наблюдателя, где бы он ни находился.',
                '\u2003Это и есть основа, исток ТО. Физический смысл относительности времени.',
                '\u2003Природная закономерность в устройстве “часовых поясов” вселенной.',
            ],
            'en': [
                'Cosmic time is determined by the distance that light travels during that time.',
                '\u2003That is, the greater the distance covered by photons, the more time has elapsed.',
                '\u2003 We see light later than the emission of photons occurred. The farther away from us that emission took place, the later we see it. Conclusion: all “events” are situated in a different time, in the past relative to the observer’s own time. That is, according to how far the “events” are from the observer, depending on the conventional value of the time coordinates of the observer’s location, there is a decrease in the absolute values of positive quantities denoting time, or an increase in the absolute values of negative time quantities for the observed “event”. Moreover, this principle applies to any observer, wherever they may be.',
                '\u2003This is the foundation, the origin of the theory of relativity. The physical meaning of the relativity of time.',
                '\u2003A natural regularity in the arrangement of the universe’s “time zones”.',
            ],
        }
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/time-zones-of-the-universe/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(
                r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(paragraphs, expected[language])
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label +
                '<a href="https://samlib.ru/b/berezina_e_l/xfcjdstgjzcf.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content")
                        for a in page.matching("meta")}
            title = "Часовые пояса Вселенной" if language == "ru" else "Time Zones of the Universe"
            self.assertEqual(metadata["og:title"], title)
            self.assertEqual(metadata["twitter:title"], title)
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(metadata["og:type"], "article")
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/time-zones-of-the-universe/"
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
        baseline = "758aefc167e23919ef7de2dac4ba38fdf02dfdf8"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith(("/articles/time-zones-of-the-universe/", "/articles/undoubtedly/"))

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
                            r'articles/(?:time-zones-of-the-universe|undoubtedly)/">.*?</div>\n', "", source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)


if __name__ == "__main__":
    unittest.main()
