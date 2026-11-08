"""Operator-supplied Article #15 text must remain exact in both languages."""
from html import unescape
import re
import unittest
import json
import subprocess
from tools import generate_publication as g

PARAGRAPHS = {'ru': ['\u2003  1. Создатель системы "ВСЕ СУЩЕЕ" не может находиться ВНЕ системы, так как если он не входит в систему , определяемую как "Все Существующее", то он просто-напросто НЕ СУЩЕCТВУЕТ.', '\u2003  2. Он не может и входить в систему "ВСЕ СУЩЕЕ" как ее часть, наряду со своим творением, потому что часть всегда проще целого, а создатель не может быть проще созданной им системы.', '\u2003  3. Остается единственный выход: отождествить Творца с Творением:\n\u2003  СОЗДАТЕЛЬ ЕСТЬ ВСЕ СУЩЕЕ.'], 'en': ['1. The creator of the system "ALL THAT EXISTS" cannot be OUTSIDE the system, because if he is not included in the system defined as "All That Exists", then he simply DOES NOT EXIST.', '2. Nor can he be part of the system "ALL THAT EXISTS", alongside his creation, because a part is always simpler than the whole, and the creator cannot be simpler than the system he has created.', '3. Only one way out remains: to identify the Creator with Creation:\nTHE CREATOR IS ALL THAT EXISTS.']}

class CageForGodTests(unittest.TestCase):
    def test_existing_records_bodies_and_discovery_entries_are_preserved(self):
        baseline = '32e52e555cb374351e58d3e0de96b9fd1117db46'
        def old(name):
            return subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=g.ROOT)
        def is_new(path):
            return path.endswith('/articles/a-cage-for-god/')
        catalog = g.load_json(g.ROOT / 'publication/catalog.json')
        previous = json.loads(old('publication/catalog.json'))
        catalog['pages'] = [p for p in catalog['pages'] if not is_new(p['path'])]
        catalog['alternate_groups'] = [p for p in catalog['alternate_groups'] if not is_new(p['ru'])]
        catalog['works']['items'] = [p for p in catalog['works']['items'] if not is_new(p['path'])]
        self.assertEqual(catalog, previous)
        authored = [p['path'].lstrip('/') + 'index.html' for p in previous['pages']
                    if not g.is_article_listing(p['path']) and p['path'] not in ('/works/', '/en/works/')]
        self.assertEqual(subprocess.check_output(['git', 'diff', baseline, '--', *authored], cwd=g.ROOT), b'')
        for name, key in [('api/agent-feed/v1.json', 'entries'), ('assets/search-index.json', 'pages'), ('assets/search-index-en.json', 'pages')]:
            current = json.loads((g.ROOT / name).read_bytes())
            current[key] = [p for p in current[key] if not is_new(p.get('url', p.get('id', ''))) ]
            self.assertEqual(current, json.loads(old(name)), name)
        for prefix in ('', 'en/'):
            name = prefix + 'articles/page-4/index.html'
            source = (g.ROOT / name).read_text(encoding='utf-8')
            source = re.sub(r'\n        <div class="item">\n          <a href="/' + prefix + r'articles/a-cage-for-god/">.*?</div>\n', '', source, flags=re.S)
            self.assertEqual(source, old(name).decode(), name)

    def test_exact_text_and_source_label(self):
        for lang, prefix in (("ru", ""), ("en", "en/")):
            route = "/" + prefix + "articles/a-cage-for-god/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = [unescape(p) for p in re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)]
            self.assertEqual(paragraphs, PARAGRAPHS[lang])
            self.assertEqual([p.lstrip().split(".")[0] for p in paragraphs], ["1", "2", "3"])
            self.assertEqual(len(paragraphs[-1].splitlines()), 2)
            self.assertIn('href="https://samlib.ru/b/berezina_e_l/rktnrflkz.shtml">Samlib</a>', source)
            self.assertIn("независимо не подтверждены" if lang == "ru" else "not independently verified", source)
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertTrue(metadata["description"])
            for key in ("og:description", "twitter:description"):
                self.assertEqual(metadata[key], metadata["description"])
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for language, start in (("ru", ""), ("en", "en/")):
                self.assertTrue(any(a.get("hreflang") == language and a.get("href") == "/" + start + "articles/a-cage-for-god/" for a in page.matching("a")))

if __name__ == "__main__":
    unittest.main()
