"""Article #20: supplied Unicode, whitespace, metadata and preservation."""
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


TEXT = {
    "ru": ''' 
 Я же здесь не новую религию вам впариваю, не тот случай.
 Мой дурной характер, неуважение к глупости и непопулярные в СИ политические взгляды не снижают доказательной ценности моей идеи, так что, если не хотите вникать в подробности, просто запомните следующее:
 
 Только для обладающих положительной массой тел, чья скорость ниже световой, закон причинности таков, каким мы наблюдаем его в нашем повседневном вещественнном мире, где время идет из прошлого в будущее.
 Для физических объектов, перемещающихся со скоростью света, причина и следствие одномоментны: в нескольких, во многих местах сразу оказывается частица, обретая свойства волны (и в путь отправляется, и цели достигает синхронно).
 При сверхсветовых скоростях следствие и вовсе опережает причину: объект достигнет цели раньше, чем с места тронулся. Именно в таком, обратном(отрицательном), времени существует антивещество.
 Этот мир визуально нами не регистрируется(по крайней мере, в варианте "макро-").
 Но ничего крамольного. Ещё Эйнштейн утверждал: "Мы вынуждены считать возможным механизм передачи сигнала, при использовании которого достигаемое следствие предшествует причине. Этот результат не содержит в себе никаких логических противоречий".
 
  Во времена Эйнштейна исследователи не умели фиксировать сверхсветовые скорости.
 Сегодня возможность превышения скорости света многократно доказана экспериментально.
 То есть, с некоторыми уточнениями и поправками, ТО наконец-то может быть реализована в полной мере.''',
    "en": ''' 
 I'm not trying to sell you a new religion here; this isn't that sort of thing.
 My bad temper, my lack of respect for stupidity, and my political views, unpopular on SI, do not diminish the evidential value of my idea. So, if you don't want to delve into the details, just remember the following:
 
 Only for bodies possessing positive mass and moving at less than the speed of light does the law of causality operate as we observe it in our everyday material world, where time flows from past to future.
 For physical objects traveling at the speed of light, cause and effect are simultaneous: a particle finds itself in several, indeed many, places at once, acquiring the properties of a wave (setting off on its journey and reaching its destination synchronously).
 At superluminal speeds, the effect actually precedes the cause: an object reaches its destination before it has even started moving. It is in precisely such reversed (negative) time that antimatter exists.
 We cannot visually detect this world (at least not in its “macro-” form).
 But there is nothing heretical about it. Einstein himself asserted: "We are compelled to regard as possible a mechanism for transmitting a signal in which the resulting effect precedes the cause. This result contains no logical contradictions."
 
  In Einstein's time, researchers did not know how to detect superluminal speeds.
 Today, the possibility of exceeding the speed of light has been demonstrated experimentally many times.
 That is, with certain clarifications and corrections, the theory of relativity can finally be implemented in full.''',
}


class EpatazhkaTests(unittest.TestCase):
    def test_exact_text_metadata_and_discovery(self):
        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        articles = [w["path"] for w in catalog["works"]["items"] if w["type"] == "article"]
        self.assertEqual(articles[-3:-1], ["/articles/the-creators-lot/", "/articles/epatazhka/"])
        self.assertEqual(len(articles), 38)
        for language, prefix, title in (("ru", "", "ЭПАТАЖКА"), ("en", "en/", "Épatage")):
            route = "/" + prefix + "articles/epatazhka/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)
            self.assertEqual([unescape(p) for p in paragraphs], TEXT[language].split("\n"))
            self.assertIn('<h1><strong>' + title + '</strong></h1>', source)
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label + '<a href="https://samlib.ru/b/berezina_e_l/248gfnf230rf.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertEqual(metadata["og:title"], title)
            self.assertEqual(metadata["twitter:title"], title)
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/epatazhka/"
                self.assertIn({"rel": "alternate", "hreflang": lang, "href": g.SITE + target}, page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == lang]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == language else None)
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"] if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text + " " + label + "Samlib.")

    def test_previous_publications_and_records_are_unchanged(self):
        baseline = "61b0ce6812017830faaa7d31ecbd52cfbebdc69a"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith(("/articles/epatazhka/", "/articles/in-another-dimension/"))

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
                            r'articles/(?:epatazhka|in-another-dimension)/">.*?</div>\n', "", source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)


if __name__ == "__main__":
    unittest.main()
