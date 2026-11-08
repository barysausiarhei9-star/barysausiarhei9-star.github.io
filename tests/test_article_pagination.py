"""Article listing boundaries use temporary catalogs, never production fake articles."""
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

from tools import generate_publication as g


class ArticlePaginationTests(unittest.TestCase):
    def fixture(self, root, count):
        production = g.load_json(g.ROOT / 'publication/catalog.json')
        catalog = {k: production[k] for k in ('format_version', 'site_url', 'rss_channel')}
        catalog.update(pages=[], alternate_groups=[], works={'version': 1, 'items': [], 'excluded_content': []},
                       navigation={'version': 1, 'aria_label': {'ru': 'Menu', 'en': 'Menu'}, 'items': [
                           {'id': 'articles', 'labels': {'ru': 'Articles', 'en': 'Articles'},
                            'targets': {'ru': '/articles/', 'en': '/en/articles/'}, 'match': 'section'}]})
        for number in range(count):
            group = {lang: ('/en' if lang == 'en' else '') + f'/articles/test-{number}/' for lang in ('ru', 'en')}
            catalog['alternate_groups'].append(group)
            catalog['works']['items'].append({'path': group['ru'], 'type': 'article'})
            for lang, route in group.items():
                title = f'{lang} article {number}'
                card = f'        <div class="item"><a href="{route}">{title}</a><p>Description {number}</p></div>'
                catalog['pages'].append(dict(path=route, title=title, language=lang, page_type='content',
                                             text_availability='html_text', rss=True, listing_card=card))
                target = root / (route.lstrip('/') + 'index.html')
                target.parent.mkdir(parents=True)
                target.write_bytes(g.with_analytics((f'<html lang="{lang}"><head><title>{title}</title></head>'
                    f'<body><header><!-- site-nav:start -->\n<nav class="site-nav" aria-label="Menu"><a href="/articles/">Articles</a></nav>\n<!-- site-nav:end --></header><main><p>Original article body {number}</p></main>'
                    + ''.join(f'<a hreflang="{key}" href="{value}">{key}</a>' for key, value in group.items())
                    + '</body></html>').encode()))
        for name in ('api/agent-feed/v1.schema.json', 'publication/templates/articles-ru.html',
                     'publication/templates/articles-en.html', 'tools/generate_publication.py', 'tools/search_index.py'):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(g.ROOT / name, target)
        for name in g.OUTPUTS:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'')
        for page in catalog['pages']:
            target = root / (page['path'].lstrip('/') + 'index.html')
            target.write_bytes(g.replace_navigation_region(target.read_bytes(), g.render_navigation(g.article_catalog(catalog), page['path'])))
        (root / 'publication/catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
        return catalog

    def quiet_run(self, root, write=False):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return g.run(root, write=write)

    def test_boundaries_order_navigation_sitemap_and_idempotence(self):
        for count in (1, 10, 11, 20, 21, 30, 31, 32, 40, 41, 50, 51, 60, 61, 70, 71):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                catalog = self.fixture(root, count)
                bodies = {p: p.read_bytes() for p in root.glob('**/test-*/index.html')}
                self.assertEqual(self.quiet_run(root), 1)
                self.assertEqual(self.quiet_run(root, True), 0)
                self.assertEqual(self.quiet_run(root), 0)
                outputs = g.render(root)
                pages = (count + 9) // 10
                expected_routes = {g.article_route(lang, n) for n in range(1, pages+1) for lang in ('ru', 'en')}
                sitemap = ET.fromstring(outputs['sitemap.xml'])
                urls = {e.text for e in sitemap.findall('{*}url/{*}loc')}
                self.assertEqual(urls, {g.SITE + p['path'] for p in catalog['pages']} | {g.SITE + p for p in expected_routes})
                for node in sitemap.findall('{*}url'):
                    route = node.find('{*}loc').text.removeprefix(g.SITE)
                    if route in expected_routes:
                        number = int(re.search(r'page-(\d+)/', route)[1]) if 'page-' in route else 1
                        self.assertEqual({a.get('hreflang'): a.get('href') for a in node.findall('{*}link')},
                                         {lang: g.SITE + g.article_route(lang, number) for lang in ('ru', 'en')})
                for lang in ('ru', 'en'):
                    order = []
                    for n in range(1, pages+1):
                        route = g.article_route(lang, n)
                        source = outputs[route.lstrip('/') + 'index.html'].decode()
                        html = g.PageHTML(source)
                        cards = re.findall(r'<div class="item">.*?</div>', source, re.S)
                        self.assertEqual(len(cards), min(10, count-(n-1)*10))
                        order.extend(re.search(r'href="([^"]+)"', card)[1] for card in cards)
                        self.assertEqual(len(html.matching('strong')), 2)
                        for rel, delta in (('prev', -1), ('next', 1)):
                            self.assertEqual([a['href'] for a in html.matching('a') if a.get('rel') == rel],
                                [g.article_route(lang, n+delta)] * (2 if 1 <= n+delta <= pages else 0))
                        numbered = [a['href'] for a in html.matching('a') if a.get('aria-label', '').startswith(('Page ', 'Страница '))]
                        self.assertEqual(numbered, [g.article_route(lang, i) for i in range(1, pages+1) if i != n] * 2)
                        self.assertIn({'rel': 'canonical', 'href': g.SITE + route}, html.matching('link'))
                        self.assertIn({'property': 'og:url', 'content': g.SITE + route}, html.matching('meta'))
                        for key, value in (('property', 'og:title'), ('name', 'twitter:title')):
                            self.assertIn({key: value, 'content': g.article_title(lang, n)}, html.matching('meta'))
                        for alternate in ('ru', 'en'):
                            target = g.article_route(alternate, n)
                            self.assertIn({'rel': 'alternate', 'hreflang': alternate, 'href': g.SITE+target}, html.matching('link'))
                            self.assertTrue(any(a.get('href') == target and a.get('hreflang') == alternate for a in html.matching('a')))
                        self.assertEqual(source.count(g.BEACON_URL), 1)
                        self.assertIn(f'Description {(n-1)*10}', source)
                    self.assertEqual(order, [group[lang] for group in catalog['alternate_groups']])
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.quiet_run(root, True), 0)
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})
                self.assertEqual(bodies, {p: p.read_bytes() for p in bodies})
                target = root / (g.article_route('en', pages).lstrip('/') + 'index.html')
                target.unlink()
                self.assertEqual(self.quiet_run(root), 1)
                if count == 31:
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    result = subprocess.run([sys.executable, '-B', str(root / 'tools/generate_publication.py'), '--check'], capture_output=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(b'en/articles/page-4/index.html', result.stderr)
                    self.assertEqual(before, {p: p.read_bytes() for p in before})
                self.assertEqual(self.quiet_run(root, True), 0)
                target.write_bytes(target.read_bytes().replace(b'Description', b'Stale description'))
                self.assertEqual(self.quiet_run(root), 1)
                if count == 31:
                    result = subprocess.run([sys.executable, '-B', str(root / 'tools/generate_publication.py'), '--check'], capture_output=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(b'en/articles/page-4/index.html', result.stderr)
                self.assertEqual(self.quiet_run(root, True), 0)

    def test_obsolete_pages_are_reported_and_never_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 1)
            target = root / 'articles/page-5/index.html'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'historical content')
            for write in (False, True):
                with self.assertRaisesRegex(g.Invalid, 'obsolete article listing pages'):
                    self.quiet_run(root, write)
                self.assertEqual(target.read_bytes(), b'historical content')

    def test_invalid_listing_inputs_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self.fixture(root, 11)
            listing = next(p for p in g.article_catalog(original)['pages'] if g.is_article_listing(p['path']))
            variants = []
            catalog = copy.deepcopy(original)
            catalog['pages'][0].pop('listing_card')
            variants.append(catalog)
            catalog = copy.deepcopy(original)
            catalog['pages'][0]['listing_card'] = '<div class="item"><a href="/wrong/">Wrong</a></div>'
            variants.append(catalog)
            catalog = copy.deepcopy(original)
            catalog['alternate_groups'].pop(0)
            variants.append(catalog)
            catalog = copy.deepcopy(original)
            catalog['pages'].extend([listing, listing])
            variants.append(catalog)
            for catalog in variants:
                with self.subTest(catalog=catalog['pages'][0]['path']):
                    (root / 'publication/catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    with self.assertRaises(g.Invalid):
                        self.quiet_run(root, True)
                    self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_first_three_listings_match_baseline_and_all_outputs_are_fresh(self):
        outputs = g.render()
        for name, data in outputs.items():
            self.assertEqual(data, (g.ROOT / name).read_bytes(), name)
            if not g.is_article_listing("/" + name.removesuffix("index.html")) or "/page-4/" in "/" + name:
                continue  # Article #15 preservation tests cover changed discovery outputs and page four.
            baseline = subprocess.check_output(
                ['git', 'show', 'b457e388af8cd0936d2521fb43a9809c0c6786c4:' + name], cwd=g.ROOT)
            self.assertEqual(data, baseline, name)
        pairs = g.article_pairs(g.load_json(g.ROOT / 'publication/catalog.json'))
        self.assertEqual(len(pairs), 32)
        for lang in ('ru', 'en'):
            actual = []
            for n in range(1, 5):
                data = outputs[g.article_route(lang, n).lstrip('/')+'index.html'].decode()
                actual.extend(re.search(r'href="([^"]+)"', card)[1]
                              for card in re.findall(r'<div class="item">.*?</div>', data, re.S))
            self.assertEqual(actual, [pair[lang]['path'] for pair in pairs])


if __name__ == '__main__':
    unittest.main()
