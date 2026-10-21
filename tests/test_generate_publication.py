"""Focused M2.2 regression and fail-closed tests; no network or repository writes."""

import copy
import hashlib
import json
from pathlib import Path
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

    def test_m1_equivalence_and_inventory(self):
        outputs = generator.render(self.root)
        for name, data in outputs.items():
            original = subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=ROOT)
            if name.endswith(".json"):
                self.assertEqual(json.loads(data), json.loads(original))
            else:
                self.assertEqual(xml_semantics(data), xml_semantics(original))
            # Stronger than semantic equivalence for this seed: canonical bytes match M1.
            self.assertEqual(data, original)
        catalog, feed, groups = generator.prepare(self.root)
        self.assertEqual(len(feed["entries"]), 59)
        self.assertEqual(sum(p["rss"] for p in catalog["pages"]), 45)
        self.assertEqual(len(catalog["alternate_groups"]), 14)
        self.assertEqual(len(groups), 28)
        self.assertEqual(sum(len(p.get("resources", [])) for p in catalog["pages"]), 4)
        self.assertEqual(sum(p["page_type"] == "placeholder" for p in catalog["pages"]), 4)
        self.assertEqual(sum(p["text_availability"] == "image_only" for p in catalog["pages"]), 3)

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

    def test_write_is_deterministic_and_touches_only_three_outputs(self):
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


if __name__ == "__main__":
    unittest.main()
