"""Focused M2.2 regression and fail-closed tests; no network or repository writes."""

import copy
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from jsonschema.exceptions import SchemaError, ValidationError
from referencing.exceptions import Unresolvable

from tools import generate_publication as generator


BASELINE = "28b0ff50e92c7ca2a3f216c2dc38770c244a5d43"
ROOT = generator.ROOT


def xml_semantics(data):
    def node(element):
        return (element.tag, sorted(element.attrib.items()), (element.text or "").strip(),
                [node(child) for child in element])
    return node(ET.fromstring(data))


def snapshot(root):
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                          p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = generator.load_json(ROOT / "publication/catalog.json")
        cls.pdfs = [p.decode("utf-8") for p in subprocess.check_output(
            ["git", "ls-files", "-z", "*.pdf"], cwd=ROOT).split(b"\0") if p]
        cls.pdfs = sorted(set(cls.pdfs) | {
            r["url"].removeprefix(generator.SITE + "/") for p in cls.catalog["pages"]
            for r in p.get("resources", []) if r["content_type"] == "application/pdf"})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        files = {"publication/catalog.json", "api/agent-feed/v1.schema.json",
                 "tools/generate_publication.py", "tools/search_index.py",
                 *generator.OUTPUTS, *self.pdfs}
        for page in self.catalog["pages"]:
            files.add(page["path"].lstrip("/") + "index.html")
            files.update(r["url"].removeprefix(generator.SITE + "/")
                         for r in page.get("resources", []))
        for name in files:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def save_catalog(self, catalog):
        (self.root / "publication/catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    def reject_without_writes(self):
        before = snapshot(self.root)
        with self.assertRaises((ValueError, OSError, SchemaError, ValidationError, Unresolvable)):
            generator.run(self.root, write=True)
        self.assertEqual(snapshot(self.root), before)

    def cli(self, mode=None):
        return subprocess.run(
            [sys.executable, "-B", "tools/generate_publication.py"] + ([mode] if mode else []),
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False)

    def check_cli_rejects_without_writes(self, *names):
        before = snapshot(self.root)
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in names:
            self.assertIn(name, result.stderr)
        self.assertEqual(snapshot(self.root), before)

    def new_publication(self, language, rss):
        path = ("/en/articles/" if language == "en" else "/articles/")
        path += "m2-probe-" + ("rss" if rss else "no-rss") + "/"
        title = "M2 English probe" if language == "en" else "Пробная публикация M2"
        body = ("A unique English publication." if language == "en"
                else "Уникальный текст русской публикации.") + f" RSS={rss}."
        target = self.root / path.lstrip("/") / "index.html"
        target.parent.mkdir(parents=True)
        target.write_text(
            f'<html lang="{language}"><head><title>{title}</title></head>'
            f'<body><main><h1>{title}</h1><p>{body}</p></main></body></html>', encoding="utf-8")
        catalog = generator.load_json(self.root / "publication/catalog.json")
        catalog["pages"].append({"path": path, "title": title, "language": language,
                                 "page_type": "content", "text_availability": "html_text",
                                 "rss": rss})
        if "works" in catalog:
            catalog["works"]["items"].append({"path": path, "type": "article"})
        if "navigation" in catalog:
            nav = generator.render_navigation(catalog, path)
            target.write_bytes(target.read_bytes().replace(b"<body><main>",
                b"<body><header>" + generator.NAV_START + b"\n" + nav +
                generator.NAV_END + b"</header><main>"))
        self.save_catalog(catalog)
        return {"url": generator.SITE + path, "title": title, "language": language, "text": body}

    def assert_new_publications(self, language):
        own = "assets/search-index-en.json" if language == "en" else "assets/search-index.json"
        other = "assets/search-index.json" if language == "en" else "assets/search-index-en.json"
        for rss in (True, False):
            with self.subTest(language=language, rss=rss):
                original = {name: (self.root / name).read_bytes() for name in generator.OUTPUTS}
                page = self.new_publication(language, rss)
                changed = {"sitemap.xml", "api/agent-feed/v1.json", own}
                changed.update(generator.WORK_OUTPUTS)
                if rss:
                    changed.add("feed.xml")
                self.check_cli_rejects_without_writes(*changed)
                before = snapshot(self.root)
                result = self.cli("--write")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                after = snapshot(self.root)
                self.assertEqual({name for name in after if after[name] != before[name]}, changed)
                generated = {name: (self.root / name).read_bytes() for name in generator.OUTPUTS}
                self.assertEqual(generated[other], original[other])
                self.assertEqual(json.loads(generated[own])["pages"], sorted(
                    json.loads(original[own])["pages"] + [page], key=lambda p: p["url"]))
                before_feed = json.loads(original["api/agent-feed/v1.json"])
                after_feed = json.loads(generated["api/agent-feed/v1.json"])
                self.assertEqual(after_feed["entries"][:-1], before_feed["entries"])
                self.assertEqual(after_feed["entries"][-1]["canonical_url"], page["url"])
                ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
                before_urls = list(ET.fromstring(original["sitemap.xml"]))
                after_urls = list(ET.fromstring(generated["sitemap.xml"]))
                self.assertEqual([xml_semantics(ET.tostring(e)) for e in after_urls[:-1]],
                                 [xml_semantics(ET.tostring(e)) for e in before_urls])
                self.assertEqual(after_urls[-1].findtext(ns + "loc"), page["url"])
                before_items = ET.fromstring(original["feed.xml"]).findall("channel/item")
                after_items = ET.fromstring(generated["feed.xml"]).findall("channel/item")
                self.assertEqual([xml_semantics(ET.tostring(e)) for e in after_items[:len(before_items)]],
                                 [xml_semantics(ET.tostring(e)) for e in before_items])
                self.assertEqual(len(after_items), len(before_items) + int(rss))
                if rss:
                    self.assertEqual(after_items[-1].findtext("link"), page["url"])
                for mode in ("--check", "--write"):
                    result = self.cli(mode)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(snapshot(self.root), after)

    def test_new_russian_publications_update_only_relevant_outputs(self):
        self.assert_new_publications("ru")

    def test_new_english_publications_update_only_relevant_outputs(self):
        self.assert_new_publications("en")

    def test_cli_rejects_stale_missing_and_corrupted_outputs_read_only(self):
        for name in generator.OUTPUTS:
            target = self.root / name
            original = target.read_bytes()
            for state in ("stale", "missing", "corrupted"):
                with self.subTest(output=name, state=state):
                    try:
                        if state == "missing":
                            target.unlink()
                        elif state == "corrupted":
                            target.write_bytes(b"{")
                        elif name.endswith(".json"):
                            data = json.loads(original)
                            data["pages" if "search-index" in name else "entries"][0]["title"] = "Stale title"
                            target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                        else:
                            target.write_bytes(original + b"\n")
                        self.check_cli_rejects_without_writes(name)
                    finally:
                        target.write_bytes(original)

    def test_m1_preservation_and_reviewed_novel_inventory(self):
        outputs = generator.render(self.root)
        prefix = generator.SITE + "/proza/pereborsh/"
        added_indexes = {generator.SITE + p for p in
                         ("/search/", "/en/search/", "/works/", "/en/works/")}
        for name, data in outputs.items():
            if name in ("assets/search-index.json", "assets/search-index-en.json", *generator.WORK_OUTPUTS):
                continue  # New derived output has its own extraction and coverage tests.
            original = subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=ROOT)
            if name.endswith(".json"):
                current, baseline = json.loads(data), json.loads(original)
                current["entries"] = [e for e in current["entries"] if not e["id"].startswith(prefix)
                                      and e["id"] not in added_indexes]
                # Approved novel/N1 sections replaced four M1 placeholders.
                # Restore only these two historical fields for the M1 comparison.
                sections = {"/proza/", "/en/book/", "/en/prose/", "/en/poetry/"}
                for entry in current["entries"]:
                    if entry["id"] in {generator.SITE + p for p in sections}:
                        entry.update(page_type="placeholder", text_availability="heading_only")
                self.assertEqual(current, baseline)
            else:
                current = ET.fromstring(data)
                parent = current.find("channel") if name == "feed.xml" else current
                link_tag = "link" if name == "feed.xml" else "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                for child in list(parent):
                    link = child.findtext(link_tag) or ""
                    if link.startswith(prefix) or link in added_indexes:
                        parent.remove(child)
                self.assertEqual(xml_semantics(ET.tostring(current)), xml_semantics(original))
        catalog, feed, groups = generator.prepare(self.root)
        self.assertEqual(len(feed["entries"]), 92)
        self.assertEqual(sum(p["rss"] for p in catalog["pages"]), 73)
        novel = [p for p in catalog["pages"] if p["path"].startswith("/proza/pereborsh/")]
        self.assertEqual(len(novel), 29)
        self.assertEqual(sum(p["page_type"] == "content" and p["rss"] for p in novel), 28)
        self.assertEqual(len(catalog["alternate_groups"]), 15)
        self.assertEqual(len(groups), 30)
        self.assertEqual(sum(len(p.get("resources", [])) for p in catalog["pages"]), 6)
        self.assertEqual(sum(p["page_type"] == "placeholder" for p in catalog["pages"]), 0)
        for path in ("/proza/", "/en/book/", "/en/prose/", "/en/poetry/"):
            page = next(p for p in catalog["pages"] if p["path"] == path)
            self.assertEqual((page["page_type"], page["text_availability"], page["rss"]),
                             ("section_index", "html_text", False))
        self.assertEqual(sum(p["text_availability"] == "image_only" for p in catalog["pages"]), 3)

    def test_works_inventory_and_five_output_bytes_are_preserved(self):
        catalog, _, groups = generator.prepare(self.root)
        works = catalog["works"]
        self.assertEqual(catalog["format_version"], 1)
        self.assertEqual(works["version"], 1)
        self.assertEqual(len(works["items"]), 36)
        self.assertEqual({kind: sum(w["type"] == kind for w in works["items"])
                          for kind in ("book", "novel", "poem", "article")},
                         {"book": 1, "novel": 1, "poem": 24, "article": 10})
        novel = next(w for w in works["items"] if w["type"] == "novel")
        self.assertEqual(novel["path"], "/proza/pereborsh/")
        self.assertEqual(novel["parts"], ["/proza/pereborsh/vstuplenie/"] +
                         [f"/proza/pereborsh/glava-{n:02}/" for n in range(1, 28)])
        self.assertEqual(works["excluded_content"], ["/about/", "/articles/about/", "/en/about/"])
        variants = {p for w in works["items"]
                    for p in groups.get(w["path"], {"own": w["path"]}).values()}
        self.assertEqual(len(variants), 46)
        self.assertNotIn("/en/book/", variants)
        self.assertNotIn("/en/prose/", variants)
        self.assertNotIn("/en/poetry/", variants)
        poems = [w["path"] for w in works["items"] if w["type"] == "poem"]
        expected = []
        for path in ("poeziya/index.html", "poeziya/page-2/index.html", "poeziya/page-3/index.html"):
            expected.extend(re.findall(r'<a href="(/poeziya/(?!page-)[a-z0-9-]+/)"',
                                       (self.root / path).read_text(encoding="utf-8")))
        self.assertEqual(poems, expected)
        for name, data in generator.render(self.root).items():
            self.assertEqual(data, (self.root / name).read_bytes(), name)

    def test_generated_catalogs_have_exact_work_titles_versions_and_order(self):
        catalog, _, groups = generator.prepare(self.root)
        pages = {p["path"]: p for p in catalog["pages"]}
        expected_order = [w["path"] for kind in ("book", "novel", "poem", "article")
                          for w in catalog["works"]["items"] if w["type"] == kind]
        outputs = generator.render(self.root)
        self.assertEqual(set(outputs), set(generator.OUTPUTS + generator.WORK_OUTPUTS))
        for language, route in generator.WORK_ROUTES.items():
            source = outputs[route.lstrip("/") + "index.html"].decode("utf-8")
            html = generator.PageHTML(source)
            rows = [a["data-work-path"] for a in html.matching("div") if "data-work-path" in a]
            self.assertEqual(rows, expected_order)
            self.assertEqual(len(set(rows)), 36)
            self.assertEqual(len(html.matching("h1")), 1)
            self.assertEqual(len(html.matching("h2")), 4)
            self.assertEqual(len(html.matching("h3")), 36)
            self.assertEqual(html.matching("script"), [])
            self.assertEqual(html.matching("html"), [{"lang": language}])
            primary = [attrs for i, (tag, attrs) in enumerate(html.tags)
                       if tag == "a" and html.tags[i - 1][0] == "h3"]
            titles = [unescape(t) for t in re.findall(r'<h3><a[^>]*>([^<]*)</a></h3>', source)]
            expected_paths = [groups.get(p, {}).get(language, p) for p in expected_order]
            self.assertEqual([a["href"] for a in primary], expected_paths)
            expected_titles = []
            for path in expected_paths:
                title = pages[path]["title"]
                for suffix in (" — Кошка Шредингера", " — Кошка Шрёдингера", " — Schrödinger’s Cat"):
                    title = title.removesuffix(suffix)
                expected_titles.append(title)
            self.assertEqual(titles, expected_titles)
            for a in primary:
                self.assertEqual((a["lang"], a["hreflang"]),
                                 (pages[a["href"]]["language"], pages[a["href"]]["language"]))
            translations = [a for a in html.matching("a") if "data-translation" in a]
            self.assertEqual(len(translations), 10)
            self.assertTrue(all("lang" not in a for a in translations))
            self.assertTrue(all(a["class"] == "work-language-link" for a in translations))
            for work_path, a in zip([p for p in expected_order if p in groups], translations):
                other = "en" if language == "ru" else "ru"
                self.assertEqual((a["href"], a["hreflang"]), (groups[work_path][other], other))
            self.assertEqual(html.matching("body"), [{"class": "reading-page works-catalog"}])
            self.assertEqual(source.count('class="catalog-intro"'), 1)
            self.assertNotIn('class="footer-note"', source)
            if language == "en":
                self.assertEqual(source.count("<span>Russian only</span>"), 26)
                self.assertEqual(source.count("<span>English</span>"), 10)
                self.assertIn('“Russian only” marks untranslated originals.', source)
            else:
                self.assertEqual(source.count("<span>На русском</span>"), 36)
                self.assertIn("Русские оригиналы и доступные переводы", source)

    def test_catalog_display_titles_strip_only_terminal_site_branding(self):
        catalog, _, groups = generator.prepare(self.root)
        page = next(p for p in catalog["pages"] if p["path"] == "/articles/formula-boga/")
        cases = (
            ("Название — подзаголовок — Кошка Шрёдингера", "Название — подзаголовок"),
            ("Название — Кошка Шредингера", "Название"),
            ("Title — Schrödinger’s Cat", "Title"),
            ("Title — Schrödinger's Cat", "Title"),
            ("Кошка Шрёдингера о теории всего", "Кошка Шрёдингера о теории всего"),
            ("Название — Кошка Шрёдингера — продолжение", "Название — Кошка Шрёдингера — продолжение"),
            ("Переборщ — Елена Березина", "Переборщ — Елена Березина"),
        )
        for original, expected in cases:
            with self.subTest(title=original):
                page["title"] = original
                before = copy.deepcopy(catalog)
                source = generator.render_work_pages(catalog, groups)["works/index.html"].decode("utf-8")
                titles = dict((path, unescape(title)) for path, title in re.findall(
                    r'<h3><a href="([^"]+)"[^>]*>([^<]*)</a></h3>', source))
                self.assertEqual(titles[page["path"]], expected)
                self.assertEqual(catalog, before)

    def test_catalog_html_is_escaped(self):
        catalog = copy.deepcopy(self.catalog)
        page = next(p for p in catalog["pages"] if p["path"] == "/articles/formula-boga/")
        old_title = page["title"]
        page["title"] = 'A <script>alert("x")</script> & "quote"'
        encoded = 'A &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quote&quot;'
        target = self.root / "articles/formula-boga/index.html"
        target.write_text(target.read_text(encoding="utf-8").replace(
            "<title>" + old_title + "</title>", "<title>" + encoded + "</title>"), encoding="utf-8")
        self.save_catalog(catalog)
        source = generator.render(self.root)["works/index.html"].decode("utf-8")
        self.assertIn(encoded, source)
        self.assertEqual(generator.PageHTML(source).matching("script"), [])

    def test_catalog_registration_is_explicit_and_fail_closed(self):
        def page(c):
            return next(p for p in c["pages"] if p["path"] == "/works/")

        mutations = {
            "no works": lambda c: c.pop("works"),
            "one route": lambda c: c["pages"].remove(next(p for p in c["pages"] if p["path"] == "/en/works/")),
            "no group": lambda c: c["alternate_groups"].remove(generator.WORK_ROUTES),
            "invalid group container": lambda c: c.update(alternate_groups=None),
            "content": lambda c: page(c).update(page_type="content"),
            "RSS": lambda c: page(c).update(rss=True),
            "language": lambda c: page(c).update(language="en"),
            "availability": lambda c: page(c).update(text_availability="heading_only"),
            "resources": lambda c: page(c).update(resources=[]),
            "catalog as work": lambda c: c["works"]["items"].append({"path": "/works/", "type": "novel"}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                catalog = copy.deepcopy(self.catalog)
                mutate(catalog)
                self.save_catalog(catalog)
                self.reject_without_writes()

    def test_catalog_missing_and_stale_checks_are_read_only_and_write_repairs_only_outputs(self):
        for name in generator.WORK_OUTPUTS:
            target = self.root / name
            original = target.read_bytes()
            for state in ("missing", "stale", "malformed"):
                with self.subTest(name=name, state=state):
                    if state == "missing":
                        target.unlink()
                    else:
                        target.write_bytes(original + b"stale" if state == "stale" else b"<broken>")
                    for mode in (None, "--check"):
                        before = snapshot(self.root)
                        result = self.cli(mode)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn(name, result.stderr)
                        self.assertEqual(snapshot(self.root), before)
                    before = snapshot(self.root)
                    result = self.cli("--write")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    after = snapshot(self.root)
                    self.assertEqual({p for p in after if after[p] != before.get(p)}, {name})
                    self.assertEqual(target.read_bytes(), original)
        before = snapshot(self.root)
        self.assertEqual(self.cli("--write").returncode, 0)
        self.assertEqual(snapshot(self.root), before)

    def test_catalog_creation_still_requires_valid_inputs_and_all_five_old_outputs(self):
        original = {name: (self.root / name).read_bytes() for name in generator.WORK_OUTPUTS}
        for name in generator.WORK_OUTPUTS:
            (self.root / name).unlink()
            (self.root / name).parent.rmdir()
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root, write=True), 0)
        after = snapshot(self.root)
        self.assertEqual({p for p in after if after[p] != before.get(p)}, set(generator.WORK_OUTPUTS))
        for name, data in original.items():
            self.assertEqual((self.root / name).read_bytes(), data)
            (self.root / name).unlink()
        catalog = copy.deepcopy(self.catalog)
        catalog["works"]["items"].pop()
        self.save_catalog(catalog)
        self.reject_without_writes()
        self.save_catalog(self.catalog)
        (self.root / "feed.xml").unlink()
        self.reject_without_writes()

    def test_catalog_write_rejects_directory_and_alias_targets_before_writes(self):
        target = self.root / generator.WORK_OUTPUTS[0]
        target.unlink()
        target.mkdir()
        self.reject_without_writes()
        target.rmdir()
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return self.root / "index.html" if path == target else original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            self.reject_without_writes()

    def test_works_absence_preserves_legacy_publication_behavior(self):
        legacy = copy.deepcopy(self.catalog)
        legacy.pop("navigation", None)  # Legacy routes do not include navigation's Works targets.
        legacy["pages"] = [p for p in legacy["pages"] if p["path"] not in generator.WORK_ROUTES.values()]
        legacy["alternate_groups"].remove(generator.WORK_ROUTES)
        for name in generator.WORK_OUTPUTS:
            (self.root / name).unlink()
        self.save_catalog(legacy)
        original = generator.render(self.root)
        for name, data in original.items():
            (self.root / name).write_bytes(data)
        legacy.pop("works")
        self.save_catalog(legacy)
        before = snapshot(self.root)
        self.assertEqual(generator.render(self.root), original)
        self.assertEqual(generator.run(self.root), 0)
        self.assertEqual(snapshot(self.root), before)
        # Legacy catalogs can still register content without discovery metadata.
        page = self.new_publication("en", False)
        outputs = generator.render(self.root)
        self.assertIn(page, json.loads(outputs["assets/search-index-en.json"])["pages"])

    def test_work_display_order_changes_only_generated_catalogs(self):
        original = generator.render(self.root)
        catalog = copy.deepcopy(self.catalog)
        catalog["works"]["items"].reverse()
        self.save_catalog(catalog)
        prepared, _, _ = generator.prepare(self.root)
        self.assertEqual(prepared["works"]["items"], catalog["works"]["items"])
        updated = generator.render(self.root)
        self.assertEqual({name for name in original if original[name] != updated[name]},
                         set(generator.WORK_OUTPUTS))

    def test_navigation_contract_and_renderer_are_shared_by_all_pages(self):
        catalog, _, _ = generator.prepare(self.root)
        navigation = catalog["navigation"]
        self.assertEqual(navigation["version"], 1)
        self.assertEqual([i["id"] for i in navigation["items"]],
                         ["home", "articles", "book", "prose", "poetry", "about", "search", "works"])
        for page in catalog["pages"]:
            with self.subTest(path=page["path"]):
                data = generator.render_navigation(catalog, page["path"])
                source = data.decode("utf-8")
                html = generator.PageHTML(source)
                self.assertEqual(html.matching("nav"), [{"class": "site-nav",
                                 "aria-label": navigation["aria_label"][page["language"]]}])
                self.assertEqual([a["href"] for a in html.matching("a")],
                                 [i["targets"][page["language"]] for i in navigation["items"]])
                self.assertEqual([unescape(t) for t in re.findall(r'<a[^>]*>([^<]*)</a>', source)],
                                 [i["labels"][page["language"]] for i in navigation["items"]])
                self.assertEqual(len([a for a in html.matching("a") if "aria-current" in a]), 1)
        before = snapshot(self.root)
        with patch.object(generator, "render_navigation", wraps=generator.render_navigation) as renderer, \
             patch.object(generator, "replace_navigation_region", wraps=generator.replace_navigation_region) as replacer:
            self.assertEqual(generator.run(self.root, write=True), 0)
            self.assertEqual({call.args[1] for call in renderer.call_args_list},
                             {p["path"] for p in catalog["pages"]})
            self.assertEqual(replacer.call_count, 90)
        self.assertEqual(snapshot(self.root), before)
        outputs = generator.render(self.root)
        self.assertEqual(set(outputs), set(generator.OUTPUTS + generator.WORK_OUTPUTS))
        for name, data in outputs.items():
            self.assertEqual(data, (self.root / name).read_bytes(), name)

    def test_navigation_active_pages_sections_overrides_and_longest_prefix(self):
        cases = {
            "/": ("/", "page"), "/en/": ("/en/", "page"),
            "/works/": ("/works/", "page"), "/en/works/": ("/en/works/", "page"),
            "/articles/": ("/articles/", "page"),
            "/articles/about/": ("/about/", "location"),
            "/articles/formula-boga/": ("/articles/", "location"),
            "/en/articles/the-formula-of-god/": ("/en/articles/", "location"),
            "/poeziya/page-2/": ("/poeziya/", "location"),
            "/poeziya/white-thread/": ("/poeziya/", "location"),
            "/proza/pereborsh/glava-14/": ("/proza/", "location"),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                html = generator.PageHTML(generator.render_navigation(self.catalog, path).decode("utf-8"))
                active = [a for a in html.matching("a") if "aria-current" in a]
                self.assertEqual([(a["href"], a["aria-current"]) for a in active], [expected])
        catalog = copy.deepcopy(self.catalog)
        catalog["navigation"]["items"].append({"id": "deeper", "labels": {"ru": "Подраздел", "en": "Subsection"},
            "targets": {"ru": "/proza/pereborsh/", "en": "/en/articles/the-formula-of-god/"}, "match": "section"})
        html = generator.PageHTML(generator.render_navigation(catalog, "/proza/pereborsh/glava-14/").decode("utf-8"))
        self.assertEqual([a for a in html.matching("a") if "aria-current" in a],
                         [{"href": "/proza/pereborsh/", "aria-current": "location"}])
        catalog["pages"].append({"path": "/navigation-probe/", "language": "ru"})
        html = generator.PageHTML(generator.render_navigation(catalog, "/navigation-probe/").decode("utf-8"))
        self.assertFalse(any("aria-current" in a for a in html.matching("a")))
        with self.assertRaises(generator.Invalid):
            generator.render_navigation(catalog, "/unregistered/")

    def test_navigation_is_escaped_utf8_deterministic_and_preserves_item_order(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["navigation"]["aria_label"]["ru"] = 'Меню <сайта> & "ссылки"'
        catalog["navigation"]["items"][0]["labels"]["ru"] = 'Главная <script>alert("x")</script> & ещё'
        before = copy.deepcopy(catalog)
        data = generator.render_navigation(catalog, "/")
        self.assertEqual(generator.render_navigation(catalog, "/"), data)
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        html = generator.PageHTML(data.decode("utf-8"))
        self.assertEqual(html.matching("script"), [])
        self.assertIn("&lt;script&gt;", data.decode("utf-8"))
        self.assertEqual(catalog, before)
        catalog["navigation"]["aria_label"] = dict(reversed(list(catalog["navigation"]["aria_label"].items())))
        for item in catalog["navigation"]["items"]:
            for field in ("labels", "targets"):
                item[field] = dict(reversed(list(item[field].items())))
        self.assertEqual(generator.render_navigation(catalog, "/"), data)
        catalog["navigation"]["items"].reverse()
        html = generator.PageHTML(generator.render_navigation(catalog, "/").decode("utf-8"))
        self.assertEqual([a["href"] for a in html.matching("a")],
                         [i["targets"]["ru"] for i in catalog["navigation"]["items"]])

    def test_navigation_absence_preserves_legacy_seven_output_behavior(self):
        original = generator.render(self.root)
        catalog = copy.deepcopy(self.catalog)
        catalog.pop("navigation")
        self.save_catalog(catalog)
        # Legacy A3.2 catalogs have no ownership comments in generated pages.
        for name in generator.WORK_OUTPUTS:
            original[name] = original[name].replace(b"      " + generator.NAV_START + b"\n", b"").replace(
                b"      " + generator.NAV_END + b"\n", b"")
            (self.root / name).write_bytes(original[name])
        before = snapshot(self.root)
        self.assertEqual(generator.render(self.root), original)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.cli("--write").returncode, 0)
        self.assertEqual(snapshot(self.root), before)
        with self.assertRaises(generator.Invalid):
            generator.render_navigation(catalog, "/")

    def test_navigation_metadata_change_propagates_to_all_92_pages_only(self):
        pages = [p["path"].lstrip("/") + "index.html" for p in self.catalog["pages"]]
        originals = {name: (self.root / name).read_bytes() for name in pages}
        protected = {name: (self.root / name).read_bytes() for name in generator.OUTPUTS}
        catalog = copy.deepcopy(self.catalog)
        catalog["navigation"]["items"].reverse()
        self.save_catalog(catalog)
        for mode in (None, "--check"):
            before = snapshot(self.root)
            self.assertEqual(self.cli(mode).returncode, 1)
            self.assertEqual(snapshot(self.root), before)
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root, write=True), 0)
        after = snapshot(self.root)
        self.assertEqual({p for p in after if after[p] != before.get(p)}, set(pages))
        for name, original in originals.items():
            updated = (self.root / name).read_bytes()
            self.assertEqual(updated.split(generator.NAV_START)[0], original.split(generator.NAV_START)[0])
            self.assertEqual(updated.split(generator.NAV_END)[1], original.split(generator.NAV_END)[1])
            menu = generator.PageHTML(re.search(rb'<nav class="site-nav"[^>]*>[\s\S]*?</nav>', updated).group().decode("utf-8"))
            locale = next(p["language"] for p in catalog["pages"] if p["path"].lstrip("/") + "index.html" == name)
            self.assertEqual([a["href"] for a in menu.matching("a")],
                             [i["targets"][locale] for i in catalog["navigation"]["items"]])
        for name, data in protected.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertEqual(self.cli("--check").returncode, 0)
        stable = snapshot(self.root)
        self.assertEqual(generator.run(self.root, write=True), 0)
        self.assertEqual(snapshot(self.root), stable)

    def test_authored_navigation_drift_is_read_only_then_repairs_only_owned_region(self):
        name = "poeziya/white-thread/index.html"
        target = self.root / name
        original = target.read_bytes()
        target.write_bytes(original.replace("Главная".encode("utf-8"), b"Menu drift probe", 1))
        for mode in (None, "--check"):
            before = snapshot(self.root)
            result = self.cli(mode)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(name, result.stderr)
            self.assertEqual(snapshot(self.root), before)
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root, write=True), 0)
        after = snapshot(self.root)
        self.assertEqual({p for p in after if after[p] != before[p]}, {name})
        self.assertEqual(target.read_bytes(), original)

    def test_missing_duplicate_or_malformed_authored_regions_prevent_all_writes(self):
        early = self.root / "index.html"
        early.write_bytes(early.read_bytes().replace("Главная".encode("utf-8"), b"Early drift", 1))
        generated = self.root / generator.WORK_OUTPUTS[0]
        generated.write_bytes(generated.read_bytes() + b"stale output")
        target = self.root / "en/search/index.html"
        original = target.read_bytes()
        variants = [original.replace(generator.NAV_START, b""),
                    original.replace(generator.NAV_END, b""),
                    original.replace(generator.NAV_START, generator.NAV_START * 2),
                    original.replace(generator.NAV_END, generator.NAV_END * 2),
                    original.replace(b'<nav class="site-nav"', b'<nav class="other-nav"'),
                    original.replace(generator.NAV_END, b'<p>Unowned content</p>' + generator.NAV_END),
                    original.replace(b'</nav>', b'</div>', 1)]
        for number, source in enumerate(variants):
            with self.subTest(variant=number):
                target.write_bytes(source)
                self.reject_without_writes()
                before = snapshot(self.root)
                for mode in (None, "--check", "--write"):
                    self.assertEqual(self.cli(mode).returncode, 1)
                    self.assertEqual(snapshot(self.root), before)

    def test_all_authored_targets_are_preflighted_before_navigation_writes(self):
        early = self.root / "index.html"
        early.write_bytes(early.read_bytes().replace("Главная".encode("utf-8"), b"Early drift", 1))
        target = self.root / "en/search/index.html"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return self.root / "index.html" if path == target else original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            self.reject_without_writes()

    def test_authored_file_changed_after_planning_is_not_overwritten(self):
        target = self.root / "en/search/index.html"
        original = target.read_bytes()
        plan = generator.authored_navigation_plan

        def concurrent_edit(root, catalog):
            result = plan(root, catalog)
            target.write_bytes(original + b"<!-- concurrent edit -->")
            return result

        before = snapshot(self.root)
        with patch.object(generator, "authored_navigation_plan", concurrent_edit), \
             self.assertRaisesRegex(generator.Invalid, "changed during validation"):
            generator.run(self.root, write=True)
        after = snapshot(self.root)
        self.assertEqual({p for p in after if after[p] != before[p]}, {"en/search/index.html"})
        self.assertEqual(target.read_bytes(), original + b"<!-- concurrent edit -->")

    def test_invalid_navigation_fails_before_writes(self):
        def nav(c):
            return c["navigation"]

        def home(c):
            return nav(c)["items"][0]

        def about(c):
            return next(i for i in nav(c)["items"] if i["id"] == "about")

        mutations = {
            "null": lambda c: c.update(navigation=None),
            "array": lambda c: c.update(navigation=[]),
            "version": lambda c: nav(c).update(version=2),
            "boolean version": lambda c: nav(c).update(version=True),
            "string version": lambda c: nav(c).update(version="1"),
            "missing field": lambda c: nav(c).pop("aria_label"),
            "unknown field": lambda c: nav(c).update(enabled=True),
            "items empty": lambda c: nav(c).update(items=[]),
            "items object": lambda c: nav(c).update(items={}),
            "null item": lambda c: nav(c)["items"].append(None),
            "missing ID": lambda c: home(c).pop("id"),
            "bad ID": lambda c: home(c).update(id="Home page"),
            "boolean ID": lambda c: home(c).update(id=True),
            "duplicate ID": lambda c: nav(c)["items"][1].update(id=home(c)["id"]),
            "unknown item field": lambda c: home(c).update(order=1),
            "missing label locale": lambda c: home(c)["labels"].pop("en"),
            "unknown label locale": lambda c: home(c)["labels"].update(be="Дом"),
            "empty label": lambda c: home(c)["labels"].update(ru=" "),
            "label padding": lambda c: home(c)["labels"].update(ru=" Главная"),
            "label type": lambda c: home(c)["labels"].update(ru=1),
            "label newline": lambda c: home(c)["labels"].update(ru="Главная\nстраница"),
            "label unicode separator": lambda c: home(c)["labels"].update(ru="Главная\u2028страница"),
            "label NEL": lambda c: home(c)["labels"].update(ru="Главная\x85страница"),
            "label control": lambda c: home(c)["labels"].update(ru="Главная\x00"),
            "label DEL": lambda c: home(c)["labels"].update(ru="Главная\x7f"),
            "missing landmark locale": lambda c: nav(c)["aria_label"].pop("en"),
            "landmark type": lambda c: nav(c).update(aria_label="Navigation"),
            "empty landmark": lambda c: nav(c)["aria_label"].update(ru=""),
            "missing target locale": lambda c: home(c)["targets"].pop("en"),
            "unknown target locale": lambda c: home(c)["targets"].update(be="/"),
            "unknown target": lambda c: home(c)["targets"].update(ru="/missing/"),
            "target URL": lambda c: home(c)["targets"].update(ru=generator.SITE + "/"),
            "target fragment": lambda c: home(c)["targets"].update(ru="/#main"),
            "target query": lambda c: home(c)["targets"].update(ru="/?q=x"),
            "target traversal": lambda c: home(c)["targets"].update(ru="/../"),
            "target type": lambda c: home(c)["targets"].update(ru=1),
            "target language": lambda c: home(c)["targets"].update(ru="/en/"),
            "duplicate target": lambda c: nav(c)["items"][1]["targets"].update(ru="/"),
            "bad match": lambda c: home(c).update(match="prefix"),
            "home section match": lambda c: home(c).update(match="section"),
            "exceptions object": lambda c: about(c).update(active_pages=[]),
            "missing exception locale": lambda c: about(c)["active_pages"].pop("en"),
            "exception list type": lambda c: about(c)["active_pages"].update(en=None),
            "unknown exception": lambda c: about(c)["active_pages"]["ru"].append("/missing/"),
            "exception language": lambda c: about(c)["active_pages"]["ru"].append("/en/articles/"),
            "duplicate exception": lambda c: about(c)["active_pages"]["ru"].append("/articles/about/"),
            "exception collision": lambda c: home(c).update(active_pages={"ru": ["/articles/about/"], "en": []}),
            "exception shadows target": lambda c: about(c)["active_pages"]["ru"].append("/articles/"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                catalog = copy.deepcopy(self.catalog)
                mutate(catalog)
                self.save_catalog(catalog)
                self.reject_without_writes()
        self.assertEqual(self.cli("--check").returncode, 1)

    def navigation_region_fixture(self):
        old = re.search(rb'<nav class="site-nav"[^>]*>[\s\S]*?</nav>',
                        (self.root / "index.html").read_bytes()).group()
        prefix = '<!DOCTYPE html>\r\n<html lang="ru"><body><header><div class="wrap">\r\n'.encode("utf-8") + generator.NAV_START
        suffix = generator.NAV_END + ('\r\n<div class="languages"><a href="/en/" lang="en">EN</a></div>'
                  '</div></header><main><p>Авторский текст:  ё — &amp; \u2028\t конец.  </p>\r\n'
                  '<nav aria-label="По стихам"><a href="/poeziya/">Назад</a></nav></main></body></html>').encode("utf-8")
        return prefix, old, suffix

    def test_navigation_region_preserves_surrounding_bytes_and_is_idempotent(self):
        prefix, old, suffix = self.navigation_region_fixture()
        source = prefix + b"\r\n  " + old + b"\r\n" + suffix
        replacement = generator.render_navigation(self.catalog, "/articles/about/")
        before = snapshot(self.root)
        with patch.object(Path, "write_bytes", side_effect=AssertionError("pure helper must not write")):
            updated = generator.replace_navigation_region(source, replacement)
        self.assertEqual(updated, prefix + b"\n" + replacement + suffix)
        self.assertEqual(generator.replace_navigation_region(updated, replacement), updated)
        self.assertEqual(snapshot(self.root), before)

    def test_navigation_region_rejects_missing_duplicate_and_ambiguous_boundaries(self):
        prefix, old, suffix = self.navigation_region_fixture()
        start, end = generator.NAV_START, generator.NAV_END
        source = prefix + b"\n" + old + b"\n" + suffix
        variants = {
            "missing markers": source.replace(start, b"").replace(end, b""),
            "missing start": source.replace(start, b""),
            "missing end": source.replace(end, b""),
            "duplicate start": source.replace(start, start + start),
            "duplicate end": source.replace(end, end + end),
            "reversed": source.replace(start, b"PROBE").replace(end, start).replace(b"PROBE", end),
            "not header": b"<main>" + start + old + end + b"</main>",
            "script strings": b"<header><script>var html='" + start + old + end + b"';</script></header>",
            "template": b"<header><template>" + start + old + end + b"</template></header>",
            "noscript": b"<header><noscript>" + start + old + end + b"</noscript></header>",
            "duplicate primary": source.replace(end, end + old),
            "malformed nav": source.replace(b"</nav>", b"</div>", 1),
            "extra owned content": source.replace(end, b"<p>Do not delete</p>" + end),
            "language block inside region": source.replace(end, b'<div class="languages">EN</div>' + end),
            "different parents": source.replace(end, b"<div>" + end + b"</div>"),
            "markers inside nav": b"<header>" + old.replace(b">", b">" + start, 1).replace(b"</nav>", end + b"</nav>") + b"</header>",
            "invalid UTF8": source + b"\xff",
        }
        replacement = generator.render_navigation(self.catalog, "/")
        for name, data in variants.items():
            with self.subTest(name=name), self.assertRaises((generator.Invalid, UnicodeError)):
                generator.replace_navigation_region(data, replacement)

    def test_navigation_region_rejects_unsafe_replacement_markup(self):
        prefix, old, suffix = self.navigation_region_fixture()
        source = prefix + old + suffix
        valid = generator.render_navigation(self.catalog, "/")
        variants = [valid.rstrip(b"\n"), valid.replace(b"\n", b"\r\n"), valid + valid,
                    valid.replace(b'site-nav', b'other-nav'),
                    valid.replace(b'</nav>', b'<script>alert(1)</script></nav>'),
                    valid.replace(b'<a ', b'<a onclick="x" ', 1),
                    valid.replace(b'href="/"', b'href="javascript:alert(1)"', 1),
                    valid.replace(b'aria-current="page"', b'aria-current="true"'),
                    valid.replace(b'<a href="/articles/"', b'<a aria-current="location" href="/articles/"'),
                    valid.replace(b'</nav>', b'<!-- extra --></nav>'),
                    b'<!DOCTYPE html>' + valid, b'<?xml version="1.0"?>' + valid,
                    valid.replace(b'</nav>', b'extra text</nav>'),
                    valid.replace(b'</nav>', b'<span>extra</span></nav>'), b"\xff\n"]
        for data in variants:
            with self.subTest(data=data[:50]), self.assertRaises((generator.Invalid, UnicodeError)):
                generator.replace_navigation_region(source, data)

    def test_invalid_works_fail_before_any_writes(self):
        def novel(c):
            return next(w for w in c["works"]["items"] if w["type"] == "novel")

        mutations = {
            "null works": lambda c: c.update(works=None),
            "works array": lambda c: c.update(works=[]),
            "missing field": lambda c: c["works"].pop("excluded_content"),
            "unknown field": lambda c: c["works"].update(translations=[]),
            "version": lambda c: c["works"].update(version=2),
            "boolean version": lambda c: c["works"].update(version=True),
            "empty items": lambda c: c["works"].update(items=[]),
            "items object": lambda c: c["works"].update(items={}),
            "null item": lambda c: c["works"]["items"].append(None),
            "item missing path": lambda c: c["works"]["items"][0].pop("path"),
            "item missing type": lambda c: c["works"]["items"][0].pop("type"),
            "item unknown field": lambda c: c["works"]["items"][0].update(order=1),
            "invalid type": lambda c: c["works"]["items"][0].update(type="chapter"),
            "type array": lambda c: c["works"]["items"][0].update(type=[]),
            "unknown root": lambda c: c["works"]["items"][0].update(path="/missing/"),
            "root traversal": lambda c: c["works"]["items"][0].update(path="/../"),
            "root URL": lambda c: c["works"]["items"][0].update(path=generator.SITE + "/kniga/"),
            "root fragment": lambda c: c["works"]["items"][0].update(path="/kniga/#book"),
            "duplicate root": lambda c: c["works"]["items"].append(c["works"]["items"][0]),
            "duplicate translation": lambda c: c["works"]["items"].append(
                {"path": "/en/articles/the-formula-of-god/", "type": "article"}),
            "index as poem": lambda c: c["works"]["items"].append({"path": "/poeziya/", "type": "poem"}),
            "unsupported book index": lambda c: c["works"]["items"].append({"path": "/en/book/", "type": "book"}),
            "missing novel evidence": lambda c: novel(c).pop("parts"),
            "parts empty": lambda c: novel(c).update(parts=[]),
            "parts string": lambda c: novel(c).update(parts="/proza/pereborsh/vstuplenie/"),
            "parts on poem": lambda c: next(w for w in c["works"]["items"] if w["type"] == "poem").update(
                parts=["/proza/pereborsh/vstuplenie/"]),
            "unknown part": lambda c: novel(c)["parts"].append("/missing/"),
            "duplicate part": lambda c: novel(c)["parts"].append(novel(c)["parts"][0]),
            "part index": lambda c: novel(c)["parts"].append("/proza/"),
            "foreign part language": lambda c: novel(c)["parts"].append("/en/articles/the-formula-of-god/"),
            "self parent": lambda c: novel(c)["parts"].append(novel(c)["path"]),
            "cycle": lambda c: c["works"]["items"][0].update(parts=[novel(c)["path"]]),
            "shared part": lambda c: c["works"]["items"].append(
                {"path": "/about/", "type": "novel", "parts": [novel(c)["parts"][0]]}),
            "part also principal": lambda c: c["works"]["items"].append(
                {"path": "/proza/pereborsh/glava-01/", "type": "article"}),
            "part order": lambda c: novel(c)["parts"].reverse(),
            "missing part": lambda c: novel(c)["parts"].pop(),
            "missing principal": lambda c: c["works"]["items"].pop(),
            "excluded not array": lambda c: c["works"].update(excluded_content={}),
            "unknown exclusion": lambda c: c["works"]["excluded_content"].append("/missing/"),
            "index exclusion": lambda c: c["works"]["excluded_content"].append("/poeziya/"),
            "duplicate exclusion": lambda c: c["works"]["excluded_content"].append("/about/"),
            "principal exclusion": lambda c: c["works"]["excluded_content"].append("/kniga/"),
            "translated exclusion": lambda c: c["works"]["excluded_content"].append("/en/articles/the-formula-of-god/"),
            "part exclusion": lambda c: c["works"]["excluded_content"].append("/proza/pereborsh/glava-01/"),
            "missing exclusion": lambda c: c["works"]["excluded_content"].pop(),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                catalog = copy.deepcopy(self.catalog)
                mutate(catalog)
                self.save_catalog(catalog)
                self.reject_without_writes()

    def test_new_content_requires_explicit_work_classification(self):
        self.new_publication("ru", False)
        catalog = generator.load_json(self.root / "publication/catalog.json")
        catalog["works"]["items"].pop()
        self.save_catalog(catalog)
        self.reject_without_writes()

    def test_parts_require_parent_link_evidence(self):
        parent = self.root / "proza/pereborsh/index.html"
        parent.write_text(parent.read_text(encoding="utf-8").replace(
            '/proza/pereborsh/glava-05/', '/proza/pereborsh/glava-06/'), encoding="utf-8")
        self.reject_without_writes()

    def test_bilingual_parts_use_existing_translation_groups(self):
        catalog = copy.deepcopy(self.catalog)
        roots = {"ru": "/novel-probe/", "en": "/en/novel-probe/"}
        parts = {language: path + "part/" for language, path in roots.items()}
        for group, page_type in ((roots, "section_index"), (parts, "content")):
            catalog["alternate_groups"].append(group)
            for language, path in group.items():
                title = "Novel probe " + language + " " + page_type
                links = "".join(f'<a href="{target}" hreflang="{lang}">{lang}</a>'
                                for lang, target in group.items())
                if page_type == "section_index":
                    links += f'<a href="{parts[language]}">Part</a>'
                html = (f'<html lang="{language}"><head><title>{title}</title></head>'
                        f'<body><main><h1>{title}</h1><p>{title}</p>{links}</main></body></html>')
                target = self.root / path.lstrip("/") / "index.html"
                target.parent.mkdir(parents=True)
                target.write_text(html, encoding="utf-8")
                catalog["pages"].append({"path": path, "title": title, "language": language,
                                         "page_type": page_type, "text_availability": "html_text",
                                         "rss": False})
        catalog["works"]["items"].append({"path": roots["ru"], "type": "novel", "parts": [parts["ru"]]})
        self.save_catalog(catalog)
        prepared, _, groups = generator.prepare(self.root)
        self.assertEqual(len(prepared["works"]["items"]), 37)
        self.assertEqual(groups[parts["ru"]], parts)
        for missing, message in ((roots, "part language has no parent"),
                                 (parts, "part has no matching parent-language")):
            with self.subTest(missing=missing):
                invalid = copy.deepcopy(catalog)
                invalid["alternate_groups"].remove(missing)
                self.save_catalog(invalid)
                before = snapshot(self.root)
                with self.assertRaisesRegex(generator.Invalid, message):
                    generator.run(self.root, write=True)
                self.assertEqual(snapshot(self.root), before)

    def test_schema_validates_generated_and_original_feeds(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry
        schema = generator.load_json(self.root / "api/agent-feed/v1.schema.json")
        validator = Draft202012Validator(schema, registry=Registry())
        validator.validate(json.loads(generator.render(self.root)["api/agent-feed/v1.json"]))
        validator.validate(generator.load_json(self.root / "api/agent-feed/v1.json"))

    def test_check_is_read_only_for_match_and_drift(self):
        generator.run(self.root, write=True)
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root), 0)
        self.assertEqual(snapshot(self.root), before)
        (self.root / "feed.xml").write_bytes(b"drift")
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root), 1)
        self.assertEqual(snapshot(self.root), before)

    def test_cli_defaults_to_read_only_and_modes_are_exclusive(self):
        with patch.object(sys, "argv", ["generate_publication.py"]), \
                patch.object(generator, "run", return_value=0) as run:
            self.assertEqual(generator.main(), 0)
            run.assert_called_once_with(write=False)
        with patch.object(sys, "argv", ["generate_publication.py", "--check"]), \
                patch.object(generator, "run", return_value=0) as run:
            self.assertEqual(generator.main(), 0)
            run.assert_called_once_with(write=False)
        with patch.object(sys, "argv", ["generate_publication.py", "--write"]), \
                patch.object(generator, "run", return_value=0) as run:
            self.assertEqual(generator.main(), 0)
            run.assert_called_once_with(write=True)
        with patch.object(sys, "argv", ["generate_publication.py", "--write", "--check"]):
            with self.assertRaises(SystemExit) as result:
                generator.main()
            self.assertEqual(result.exception.code, 2)

    def test_write_is_deterministic_and_touches_only_publication_outputs(self):
        before = snapshot(self.root)
        self.assertEqual(generator.run(self.root, write=True), 0)
        first = snapshot(self.root)
        self.assertLessEqual({name for name in first if first[name] != before[name]},
                             set(generator.OUTPUTS + generator.WORK_OUTPUTS))
        self.assertEqual(generator.render(self.root), generator.render(self.root))
        self.assertEqual(generator.run(self.root, write=True), 0)
        self.assertEqual(snapshot(self.root), first)
        self.assertEqual(len(self.pdfs), 3)
        for pdf in self.pdfs:
            self.assertEqual(first[pdf], before[pdf])

    def test_invalid_catalogs_fail_before_writes(self):
        def resource(c):
            return next(p for p in c["pages"] if "resources" in p)["resources"][0]
        mutations = {
            "format": lambda c: c.update(format_version=2),
            "boolean format": lambda c: c.update(format_version=True),
            "unknown field": lambda c: c.update(autopublish=True),
            "site": lambda c: c.update(site_url="https://example.org"),
            "empty pages": lambda c: c.update(pages=[]),
            "missing page": lambda c: c["pages"].pop(),
            "duplicate page": lambda c: c["pages"].append(c["pages"][0]),
            "traversal": lambda c: c["pages"][0].update(path="/../"),
            "encoded traversal": lambda c: c["pages"][0].update(path="/%2e%2e/"),
            "query": lambda c: c["pages"][0].update(path="/?x=1"),
            "missing title": lambda c: c["pages"][0].pop("title"),
            "title drift": lambda c: c["pages"][0].update(title="invented"),
            "language": lambda c: c["pages"][0].update(language="de"),
            "classification": lambda c: c["pages"][0].update(page_type="novel"),
            "availability": lambda c: c["pages"][0].update(text_availability="heading_only"),
            "image without resource": lambda c: next(p for p in c["pages"] if p["text_availability"] == "image_only").pop("resources"),
            "rss type": lambda c: c["pages"][0].update(rss=1),
            "rss index": lambda c: c["pages"][0].update(rss=True),
            "channel field": lambda c: c["rss_channel"].update(pubDate="invented"),
            "channel link": lambda c: c["rss_channel"].update(link="https://example.org/"),
            "resource ID": lambda c: resource(c).update(id=generator.SITE + "/assets/other.pdf"),
            "resource language": lambda c: resource(c).update(language="en"),
            "resource title": lambda c: resource(c).update(title="invented"),
            "resource type": lambda c: resource(c).update(content_type="image/png"),
            "resource path": lambda c: resource(c).update(url=generator.SITE + "/assets/../book.pdf"),
            "duplicate resource": lambda c: next(p for p in c["pages"] if "resources" in p)["resources"].append(resource(c)),
            "missing group member": lambda c: c["alternate_groups"][0].pop("en"),
            "unknown group member": lambda c: c["alternate_groups"][0].update(en="/en/missing/"),
            "group language": lambda c: c["alternate_groups"][0].update(en="/articles/"),
            "duplicate group": lambda c: c["alternate_groups"].append(c["alternate_groups"][0]),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                catalog = copy.deepcopy(self.catalog)
                mutate(catalog)
                self.save_catalog(catalog)
                self.reject_without_writes()

    def test_duplicate_keys_and_malformed_json_fail_closed(self):
        for data in ('{"format_version":1,"format_version":1}', '{', '{"format_version":NaN}'):
            with self.subTest(data=data):
                (self.root / "publication/catalog.json").write_text(data, encoding="utf-8")
                self.reject_without_writes()

    def test_invalid_html_fails_before_writes(self):
        target = self.root / "index.html"
        original = target.read_text(encoding="utf-8")
        variants = [original.replace('<html lang="ru">', '<html lang="en">'),
                    original.replace("<title>", "<title>changed "),
                    original.replace("</main>", ""),
                    original.replace("<main>", '<main><link rel="canonical" href="https://example.org/">'),
                    original.replace("<main>", '<main><base href="https://example.org/">'),
                    original.replace('<html lang="ru">', '<html lang="ru" lang="en">')]
        for data in variants:
            with self.subTest(variant=variants.index(data)):
                target.write_text(data, encoding="utf-8")
                self.reject_without_writes()

    def test_missing_html_fails_before_writes(self):
        (self.root / "poeziya/xxl/index.html").unlink()
        self.reject_without_writes()

    def test_new_uncatalogued_html_fails_before_writes(self):
        path = self.root / "new/index.html"
        path.parent.mkdir()
        shutil.copyfile(self.root / "index.html", path)
        self.reject_without_writes()

    def test_resource_signatures_missing_files_and_html_evidence_fail_closed(self):
        pdf = self.root / "assets/books/koshka-shredingera.pdf"
        png = self.root / "assets/images/endemik.png"
        book = self.root / "kniga/index.html"
        poem = self.root / "poeziya/endemik/index.html"
        originals = {p: p.read_bytes() for p in (pdf, png, book, poem)}
        mutations = [lambda: pdf.write_bytes(b"not PDF"), lambda: png.write_bytes(b"not PNG"),
                     lambda: pdf.unlink(), lambda: png.unlink(),
                     lambda: book.write_bytes(originals[book].replace(b'application/pdf', b'application/zip')),
                     lambda: book.write_bytes(originals[book].replace(b'"inLanguage": "ru"', b'"inLanguage": "en"')),
                     lambda: poem.write_bytes(originals[poem].replace(b'alt="', b'alt="changed ')),
                     lambda: poem.write_bytes(originals[poem].replace(b'/assets/images/endemik.png', b'/assets/images/missing.png'))]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                for path, data in originals.items():
                    path.write_bytes(data)
                mutate()
                self.reject_without_writes()

    def test_missing_or_invalid_schema_fails_before_writes(self):
        schema = self.root / "api/agent-feed/v1.schema.json"
        schema.write_text('{"type":"invalid-type"}', encoding="utf-8")
        self.reject_without_writes()
        schema.unlink()
        self.reject_without_writes()

    def test_missing_output_prevents_all_writes(self):
        (self.root / "feed.xml").unlink()
        self.reject_without_writes()

    def test_html_text_edit_changes_only_search_output_and_check_detects_drift(self):
        for route, index in (("articles/formula-boga/index.html", "assets/search-index.json"),
                             ("en/articles/the-formula-of-god/index.html", "assets/search-index-en.json")):
            with self.subTest(route=route):
                original = generator.render(self.root)
                target = self.root / route
                source = target.read_bytes()
                try:
                    target.write_bytes(source.replace(b"</main>", b"<p>search drift probe</p></main>"))
                    updated = generator.render(self.root)
                    self.assertEqual([name for name in original if original[name] != updated[name]], [index])
                    self.check_cli_rejects_without_writes(index)
                finally:
                    target.write_bytes(source)

    def test_remote_schema_reference_fails_without_network(self):
        (self.root / "api/agent-feed/v1.schema.json").write_text(
            '{"$ref":"https://example.org/unavailable-schema.json"}', encoding="utf-8")
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as request:
            self.reject_without_writes()
            request.assert_not_called()

    def test_alternate_links_are_validated(self):
        page = self.root / "en/index.html"
        page.write_bytes(page.read_bytes().replace(b'hreflang="ru"', b'hreflang="de"'))
        self.reject_without_writes()


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "assets/books/probe.epub"
        self.file.parent.mkdir(parents=True)
        self.page = {"path": "/proza/pereborsh/", "language": "ru"}
        self.resource = {"id": generator.SITE + "/assets/books/probe.epub",
                         "url": generator.SITE + "/assets/books/probe.epub",
                         "content_type": "application/epub+zip", "language": "ru",
                         "title": "EPUB probe"}
        self.book = {"@type": "Book", "name": "EPUB probe", "inLanguage": "ru",
                     "encoding": {"contentUrl": self.resource["url"],
                                  "encodingFormat": "application/epub+zip"}}
        self.entries = [
            ("mimetype", b"application/epub+zip", ZIP_STORED),
            ("META-INF/container.xml", b'<container version="1.0" '
             b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             b'<rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>'
             b'</rootfiles></container>', ZIP_DEFLATED),
            ("EPUB/package.opf", b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
             b'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
             b'<dc:identifier id="id">urn:uuid:42e2624c-32d6-4f4b-8c17-394d87431461</dc:identifier>'
             b'<dc:title>EPUB probe</dc:title><dc:language>ru</dc:language>'
             b'<meta property="dcterms:modified">2026-10-27T00:00:00Z</meta></metadata><manifest>'
             b'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
             b'<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
             b'</manifest><spine><itemref idref="chapter"/></spine></package>', ZIP_DEFLATED),
            ("EPUB/nav.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" '
             b'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head>'
             b'<body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">Probe</a></li>'
             b'</ol></nav></body></html>', ZIP_DEFLATED),
            ("EPUB/chapter.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml">'
             b'<head><title>Probe</title></head><body><p>EPUB probe text.</p></body></html>', ZIP_STORED),
        ]
        self.write_epub()

    def write_epub(self, entries=None):
        with ZipFile(self.file, "w") as archive:
            for name, data, compression in self.entries if entries is None else entries:
                archive.writestr(name, data, compress_type=compression)

    def html(self, book=None, href="/assets/books/probe.epub", mime="application/epub+zip"):
        return generator.PageHTML(
            f'<a href="{href}" type="{mime}">Download</a>'
            '<script type="application/ld+json">' +
            json.dumps(self.book if book is None else book) + '</script>')

    def reject(self, resource=None, html=None, message=None):
        before = snapshot(self.root)
        with self.assertRaisesRegex(generator.Invalid, message or "."):
            generator.validate_resource(self.root, self.page,
                                        self.resource if resource is None else resource,
                                        self.html() if html is None else html)
        self.assertEqual(snapshot(self.root), before)

    def test_valid_epub_is_inspected_in_place_without_extraction(self):
        before = snapshot(self.root)
        with patch.object(ZipFile, "extract", side_effect=AssertionError("extraction forbidden")), \
                patch.object(ZipFile, "extractall", side_effect=AssertionError("extraction forbidden")):
            for href in ("/assets/books/probe.epub", "../../assets/books/probe.epub",
                         self.resource["url"]):
                with self.subTest(href=href):
                    generator.validate_resource(self.root, self.page, self.resource, self.html(href=href))
        self.assertEqual(snapshot(self.root), before)

    def test_epub_passes_publication_preparation_and_invalid_resource_prevents_writes(self):
        catalog = generator.load_json(ROOT / "publication/catalog.json")
        catalog.pop("works", None)
        catalog.pop("navigation", None)
        catalog["alternate_groups"] = []
        self.page.update(path="/", title="Probe", page_type="content",
                         text_availability="html_text", rss=False, resources=[self.resource])
        catalog["pages"] = [self.page]
        (self.root / "publication").mkdir()
        (self.root / "publication/catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        schema = self.root / "api/agent-feed/v1.schema.json"
        schema.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "api/agent-feed/v1.schema.json", schema)
        (self.root / "index.html").write_text(
            '<html lang="ru"><head><title>Probe</title></head><body><main><p>Probe text.</p>'
            '<a href="/assets/books/probe.epub" type="application/epub+zip">Download</a>'
            '<script type="application/ld+json">' + json.dumps(self.book) +
            '</script></main></body></html>', encoding="utf-8")
        before = snapshot(self.root)
        _, feed, _ = generator.prepare(self.root)
        self.assertEqual(feed["entries"][0]["resources"], [self.resource])
        self.assertEqual(snapshot(self.root), before)
        self.file.write_bytes(b"invalid EPUB")
        before = snapshot(self.root)
        with self.assertRaises(generator.Invalid):
            generator.run(self.root, write=True)
        self.assertEqual(snapshot(self.root), before)

    def test_epub_rejects_malformed_zip_and_mimetype(self):
        for data in (b"not a ZIP", self.file.read_bytes()[:-22],
                     b"prefix" + self.file.read_bytes(),
                     self.file.read_bytes().replace(b"EPUB probe text.", b"EPUB wrong text."),
                     self.file.read_bytes()[:8] + b"\x08\x00" + self.file.read_bytes()[10:]):
            with self.subTest(data=data[:20]):
                self.file.write_bytes(data)
                self.reject()
        variants = {
            "empty ZIP": [],
            "missing mimetype": self.entries[1:],
            "mimetype not first": [self.entries[1], self.entries[0], *self.entries[2:]],
            "compressed mimetype": [("mimetype", b"application/epub+zip", ZIP_DEFLATED), *self.entries[1:]],
            "wrong mimetype": [("mimetype", b"application/zip", ZIP_STORED), *self.entries[1:]],
            "mimetype whitespace": [("mimetype", b"application/epub+zip\n", ZIP_STORED), *self.entries[1:]],
            "duplicate member": [*self.entries, self.entries[2]],
        }
        for name, entries in variants.items():
            with self.subTest(name=name):
                if name == "duplicate member":
                    with self.assertWarns(UserWarning):
                        self.write_epub(entries)
                else:
                    self.write_epub(entries)
                self.reject()

    def test_epub_rejects_missing_or_malformed_container_and_package(self):
        variants = {"missing container": [self.entries[0], *self.entries[2:]],
                    "missing package": [*self.entries[:2], *self.entries[3:]]}
        for index, label, replacements in (
            (1, "container", [(None, b"<"), (b"container", b"wrong"),
                              (b"<rootfile full-path=", b"<other full-path="),
                              (b'full-path="EPUB/package.opf"', b'full-path=""'),
                              (b"EPUB/package.opf", b"../package.opf"),
                              (b"EPUB/package.opf", b"/EPUB/package.opf"),
                              (b"EPUB/package.opf", b"EPUB\\package.opf"),
                              (b"EPUB/package.opf", b"https://example.org/package.opf"),
                              (b"application/oebps-package+xml", b"application/xml")]),
            (2, "package", [(None, b"<"), (b"package", b"wrong"),
                            (b"http://www.idpf.org/2007/opf", b"urn:wrong")]),
        ):
            for number, (old, new) in enumerate(replacements):
                entries = list(self.entries)
                name, data, compression = entries[index]
                entries[index] = (name, new if old is None else data.replace(old, new), compression)
                variants[f"{label} {number}"] = entries
        for name, entries in variants.items():
            with self.subTest(name=name):
                self.write_epub(entries)
                self.reject()

    def test_epub_requires_local_file_language_id_and_safe_url(self):
        self.file.unlink()
        self.reject(message="missing file")
        self.write_epub()
        for change in ({"language": "en"}, {"id": generator.SITE + "/assets/other.epub"}):
            with self.subTest(change=change):
                self.reject(resource={**self.resource, **change})
        for url in ("https://example.org/assets/books/probe.epub",
                    generator.SITE + "/assets/../probe.epub",
                    generator.SITE + "/assets/%2e%2e/probe.epub",
                    self.resource["url"] + "?download=1", self.resource["url"] + "#book"):
            with self.subTest(url=url):
                self.reject(resource={**self.resource, "id": url, "url": url},
                            message="invalid resource URL")
        outside = Path(self.temp.name + "-outside")
        # Check the existing containment guard without creating an external file/link.
        with patch.object(Path, "resolve", side_effect=[outside, self.root]):
            self.reject(message="file escapes repository")

    def test_epub_requires_matching_typed_link_and_book_metadata(self):
        for html in (generator.PageHTML(""), self.html(href="/assets/books/other.epub"),
                     self.html(href="https://example.org/assets/books/probe.epub"),
                     self.html(mime=""), self.html(mime="application/pdf")):
            self.reject(html=html, message="missing typed EPUB link")
        for field, value in (("@type", "CreativeWork"), ("name", "Wrong title"),
                             ("inLanguage", "en"), ("encoding", None)):
            with self.subTest(field=field):
                self.reject(html=self.html(book={**self.book, field: value}), message="Book metadata")
        for field, value in (("contentUrl", generator.SITE + "/assets/books/other.epub"),
                             ("encodingFormat", "application/pdf")):
            book = {**self.book, "encoding": {**self.book["encoding"], field: value}}
            self.reject(html=self.html(book=book), message="Book metadata")
        for field in self.book:
            book = {key: value for key, value in self.book.items() if key != field}
            self.reject(html=self.html(book=book), message="Book metadata")
        self.reject(html=self.html(book=[]), message="Book metadata")

    def test_resource_schema_and_validator_reject_mime_extension_mismatches(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry
        schema = generator.load_json(ROOT / "api/agent-feed/v1.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, registry=Registry())
        entry = {"id": generator.SITE + self.page["path"],
                 "canonical_url": generator.SITE + self.page["path"], "language": "ru",
                 "content_type": "text/html", "title": "Probe", "page_type": "content",
                 "text_availability": "html_text"}
        for extension in ("pdf", "png", "epub", "zip"):
            for mime in ("application/pdf", "image/png", "application/epub+zip", "application/zip"):
                with self.subTest(extension=extension, mime=mime):
                    url = generator.SITE + "/assets/books/probe." + extension
                    resource = {**self.resource, "id": url, "url": url, "content_type": mime}
                    feed = {"$schema": generator.SCHEMA_URL, "version": "1.0.0",
                            "entries": [{**entry, "resources": [resource]}]}
                    if (extension, mime) in (("pdf", "application/pdf"), ("png", "image/png"),
                                             ("epub", "application/epub+zip")):
                        validator.validate(feed)
                    else:
                        with self.assertRaises(ValidationError):
                            validator.validate(feed)
                        target = self.file.with_suffix("." + extension)
                        if target != self.file:
                            target.write_bytes(b"%PDF-\x89PNG\r\n\x1a\n")
                            self.addCleanup(target.unlink, missing_ok=True)
                        self.reject(resource=resource)


class PagesWorkflowTests(unittest.TestCase):
    def test_read_only_gate_precedes_upload_and_deployment_without_bypasses(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        steps = re.split(r"(?m)^      - name: ", workflow)[1:]
        names = [step.splitlines()[0] for step in steps]
        order = [names.index(name) for name in (
            "Checkout", "Set up Python", "Install publication validator",
            "Check publication outputs (read-only)", "Configure Pages", "Upload artifact",
            "Deploy to GitHub Pages")]
        self.assertEqual(order, sorted(order))
        self.assertIn("run: python -m pip install -r publication/requirements.txt\n", steps[order[2]])
        self.assertIn("run: python -B tools/generate_publication.py --check\n", steps[order[3]])
        self.assertNotIn("--write", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*(if|continue-on-error):")


if __name__ == "__main__":
    unittest.main()
