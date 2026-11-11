"""Article #16: supplied paragraph fidelity and preservation of prior publications."""
import hashlib
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


class AlbinoBullTests(unittest.TestCase):
    def test_supplied_paragraphs_and_public_attribution(self):
        # SHA-256 of each complete operator-supplied paragraph, including whitespace.
        hashes = {
            "ru": ["b0a94f6952eca78347f5f036c45cc3862cb9041a7015e75a761e1ec439b091b1",
                   "c95917c8870339c8bdca8a07e91170d35837cef1e465ca2a3013424359664cb5",
                   "0536d88ff4dab60ac011b1096c6a8a68215cb53015097efaf248f79855d1492d"],
            "en": ["e03a959c536730232db13a31d2961e4d365060d35ae97c6d31f8bb3e93525fa6",
                   "11b7089c8837d59f3ed0b9559934e0ecb4cc92a7339aa9293ef418268d66fbcc",
                   "1d08a47dc667696f7f1db4d24ed892e14f71025fea17e85cf777ce1ba1f83140"],
        }
        for language, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/the-albino-bull/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(
                r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual([hashlib.sha256(p.encode()).hexdigest() for p in paragraphs], hashes[language])
            self.assertFalse(paragraphs[0].startswith("\u2003"))
            self.assertTrue(all(p.startswith("\u2003 ") for p in paragraphs[1:]))
            if language == "ru":
                self.assertIn("бОльшей", paragraphs[0])
                self.assertIn("настоящее(будущее)", paragraphs[0])
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label +
                '<a href="https://samlib.ru/b/berezina_e_l/tksqsr.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"]
                         if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text +
                             " " + label + "Samlib.")

    def test_previous_publications_and_records_are_unchanged(self):
        baseline = "8555128f9a71185afe2a4631f56a68416f633b21"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith("/articles/the-albino-bull/")

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
                            r'articles/the-albino-bull/">.*?</div>\n', "", source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)


if __name__ == "__main__":
    unittest.main()
