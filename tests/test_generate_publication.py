"""Focused M2.2 regression and fail-closed tests; no network or repository writes."""

import copy
import hashlib
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

    def cli(self, mode):
        return subprocess.run(
            [sys.executable, "-B", "tools/generate_publication.py", mode],
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
        for name, data in outputs.items():
            if name in ("assets/search-index.json", "assets/search-index-en.json"):
                continue  # New derived output has its own extraction and coverage tests.
            original = subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=ROOT)
            if name.endswith(".json"):
                current, baseline = json.loads(data), json.loads(original)
                current["entries"] = [e for e in current["entries"] if not e["id"].startswith(prefix)
                                      and e["id"] not in {generator.SITE + "/search/", generator.SITE + "/en/search/"}]
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
                    if link.startswith(prefix) or link in {generator.SITE + "/search/", generator.SITE + "/en/search/"}:
                        parent.remove(child)
                self.assertEqual(xml_semantics(ET.tostring(current)), xml_semantics(original))
        catalog, feed, groups = generator.prepare(self.root)
        self.assertEqual(len(feed["entries"]), 90)
        self.assertEqual(sum(p["rss"] for p in catalog["pages"]), 73)
        novel = [p for p in catalog["pages"] if p["path"].startswith("/proza/pereborsh/")]
        self.assertEqual(len(novel), 29)
        self.assertEqual(sum(p["page_type"] == "content" and p["rss"] for p in novel), 28)
        self.assertEqual(len(catalog["alternate_groups"]), 14)
        self.assertEqual(len(groups), 28)
        self.assertEqual(sum(len(p.get("resources", [])) for p in catalog["pages"]), 4)
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

    def test_works_absence_preserves_legacy_publication_behavior(self):
        original = generator.render(self.root)
        legacy = copy.deepcopy(self.catalog)
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

    def test_work_display_order_is_explicit_and_does_not_change_m2_outputs(self):
        original = generator.render(self.root)
        catalog = copy.deepcopy(self.catalog)
        catalog["works"]["items"].reverse()
        self.save_catalog(catalog)
        prepared, _, _ = generator.prepare(self.root)
        self.assertEqual(prepared["works"]["items"], catalog["works"]["items"])
        self.assertEqual(generator.render(self.root), original)

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
                             set(generator.OUTPUTS))
        self.assertEqual(generator.render(self.root), generator.render(self.root))
        self.assertEqual(generator.run(self.root, write=True), 0)
        self.assertEqual(snapshot(self.root), first)
        self.assertEqual(len(self.pdfs), 2)
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
