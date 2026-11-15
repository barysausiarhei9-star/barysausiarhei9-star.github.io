"""Article #25: fidelity to the supplied bilingual publication reference."""
import hashlib
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g


class IdeeFixeTests(unittest.TestCase):
    def test_complete_supplied_text_and_attribution(self):
        # Hashes cover the complete supplied body, including blank-line paragraph
        # divisions, six literal section breaks, formula and closing signature.
        # The English reference's Markdown emphasis is rendered as HTML emphasis.
        hashes = {
            "ru": "23adfef0929a13b1f6f212d3982917f1fc933cb7ae9cec395ee78d056708d3da",
            "en": "1a5f07053bf7ed356a160e590acc29eb9c1d4a31efa49332b0a194291f8b1563",
        }
        for language, prefix in (("ru", ""), ("en", "en/")):
            with self.subTest(language=language):
                source = (g.ROOT / prefix / "articles/idee-fixe-on-the-multiverse/index.html").read_text(encoding="utf-8")
                body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
                paragraphs = [unescape(re.sub(r'</?em>', '', p).replace('<br />\n', '\n'))
                              for p in re.findall(r'<p>(.*?)</p>', body, re.S)]
                self.assertEqual(len(paragraphs), 18)
                self.assertEqual(paragraphs.count("***"), 6)
                self.assertEqual(hashlib.sha256("\n\n".join(paragraphs).encode()).hexdigest(), hashes[language])
                self.assertIn('href="https://samlib.ru/b/berezina_e_l/bltahbrc.shtml"', source)
                self.assertIn('class="back" href="/' + prefix + 'articles/page-5/"', source)
                other = (g.ROOT / prefix / "articles/multiplicity-of-worlds/index.html").read_text(encoding="utf-8")
                self.assertNotIn(paragraphs[1], other)

    def test_only_new_catalog_records_and_prior_authored_pages_preserved(self):
        baseline = "37fecab2e9381537bf9b53d3720a21bf89769a6b"
        previous = json.loads(subprocess.check_output(
            ["git", "show", baseline + ":publication/catalog.json"], cwd=g.ROOT))
        current = g.load_json(g.ROOT / "publication/catalog.json")
        suffix = "/articles/idee-fixe-on-the-multiverse/"
        for key, field in (("pages", "path"), ("alternate_groups", "ru")):
            current[key] = [p for p in current[key] if not p[field].endswith(suffix)]
        current["works"]["items"] = [w for w in current["works"]["items"] if not w["path"].endswith(suffix)]
        self.assertEqual(current, previous)
        authored = [p["path"].lstrip("/") + "index.html" for p in previous["pages"]
                    if not g.is_article_listing(p["path"]) and p["path"] not in ("/works/", "/en/works/")]
        self.assertEqual(subprocess.check_output(["git", "diff", baseline, "--", *authored], cwd=g.ROOT), b"")


if __name__ == "__main__":
    unittest.main()
