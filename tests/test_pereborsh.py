"""Source-backed integrity and tampering checks; private local source is not committed."""

import hashlib
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from tools import verify_pereborsh as proof
from tools import generate_publication as generator


class PereborshDownloadTests(unittest.TestCase):
    def test_approved_download_bytes_links_and_publication_metadata_agree(self):
        catalog = generator.load_json(proof.ROOT / "publication/catalog.json")
        page = next(p for p in catalog["pages"] if p["path"] == "/proza/pereborsh/")
        html = generator.validate_html(proof.ROOT, page)
        expected = (
            ("pdf", "application/pdf", 5229145,
             "d44ab53e0fe4a5795014cd7eaf5eb9d49ec19effecda1418a838b8c3c9f7d18e"),
            ("epub", "application/epub+zip", 3780568,
             "1021a381ccec0b338a3575724419518f803534453c09354d22bbe891835b0a56"),
        )
        self.assertEqual(len(page["resources"]), 2)
        for resource, (extension, mime, size, digest) in zip(page["resources"], expected):
            with self.subTest(extension=extension):
                relative = "assets/books/pereborsh." + extension
                self.assertEqual(resource, {"id": generator.SITE + "/" + relative,
                    "url": generator.SITE + "/" + relative, "language": "ru",
                    "content_type": mime, "title": "Переборщ"})
                data = (proof.ROOT / relative).read_bytes()
                self.assertEqual(len(data), size)
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                links = [a for a in html.matching("a") if a.get("href") == "/" + relative]
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].get("type"), mime)
                self.assertEqual(links[0].get("download"), "pereborsh." + extension)
                generator.validate_resource(proof.ROOT, page, resource, html)
        feed = generator.load_json(proof.ROOT / "api/agent-feed/v1.json")
        entry = next(e for e in feed["entries"] if e["canonical_url"] == generator.SITE + page["path"])
        self.assertEqual(entry["resources"], page["resources"])

    def test_download_landing_preserves_online_reading_and_full_cover(self):
        source = (proof.ROOT / "proza/pereborsh/index.html").read_text(encoding="utf-8")
        html = generator.PageHTML(source)
        self.assertIn('(Неоконченный роман для нативного интеллекта)', source)
        self.assertIn('class="button" href="/proza/pereborsh/vstuplenie/#novel-text"', source)
        cover = next(img for img in html.matching("img") if img.get("src") ==
                     "/assets/images/pereborsh-cover.png")
        self.assertEqual((cover["width"], cover["height"]), ("1024", "1536"))
        chapters = [a["href"] for a in html.matching("a") if re.fullmatch(
            r"/proza/pereborsh/glava-\d{2}/", a.get("href", ""))]
        self.assertEqual(chapters, [f"/proza/pereborsh/glava-{n:02}/" for n in range(1, 28)])


@unittest.skipUnless((proof.ROOT / proof.SOURCE).is_file(), "private source ZIP required locally")
class PereborshTests(unittest.TestCase):
    def test_complete_source_matches_reading_pages(self):
        result = proof.verify()
        self.assertEqual((result["novel_html_pages"], result["reading_pages"]), (29, 28))
        self.assertEqual((result["paragraphs"], result["coverage_percent"]), (720, 100))

    def reject_html_mutation(self, relative, mutate):
        target = proof.ROOT / relative
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            data = original_read(path, *args, **kwargs)
            return mutate(data) if path == target else data
        with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
            proof.verify()

    def test_rewritten_punctuation_rejected(self):
        self.reject_html_mutation("proza/pereborsh/glava-01/index.html",
                                  lambda s: s.replace("Ава - это не я.", "Ава — это не я.", 1))

    def test_missing_duplicated_or_reordered_paragraph_rejected(self):
        pattern = r'(<p data-fb2-p="31">.*?</p>)(\s*)(<p data-fb2-p="32">.*?</p>)'
        for replacement in (r"\3", r"\1\2\1\2\3", r"\3\2\1"):
            with self.subTest(replacement=replacement):
                self.reject_html_mutation("proza/pereborsh/glava-01/index.html",
                    lambda s: re.sub(pattern, replacement, s, flags=re.S))

    def test_invented_unmapped_text_rejected(self):
        self.reject_html_mutation("proza/pereborsh/glava-01/index.html",
                                  lambda s: s.replace("</article>", "<p>Лишний текст.</p></article>"))

    def test_broken_navigation_rejected(self):
        self.reject_html_mutation("proza/pereborsh/glava-01/index.html",
                                  lambda s: s.replace('rel="next" href="/proza/pereborsh/glava-02/"',
                                                      'rel="next" href="/proza/pereborsh/glava-03/"'))

    def test_lost_verse_formatting_rejected(self):
        self.reject_html_mutation("proza/pereborsh/vstuplenie/index.html",
                                  lambda s: s.replace('class="verse-line"', 'class="prose"', 1))

    def test_incomplete_toc_rejected(self):
        self.reject_html_mutation("proza/pereborsh/index.html",
                                  lambda s: s.replace('href="/proza/pereborsh/glava-18/"',
                                                      'href="/proza/pereborsh/glava-17/"'))


if __name__ == "__main__":
    unittest.main()
