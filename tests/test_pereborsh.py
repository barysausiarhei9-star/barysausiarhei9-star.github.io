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


class PereborshTests(unittest.TestCase):
    def test_complete_source_matches_reading_pages(self):
        result = proof.verify()
        self.assertEqual((result["novel_html_pages"], result["reading_pages"]), (29, 28))
        self.assertEqual((result["paragraphs"], result["coverage_percent"]), (720, 100))
        self.assertEqual(result["corrected_blocks"], [614, 615, 620, 622, 624])
        self.assertEqual(result["raw_paragraphs_sha256"],
                         "ea3e4b78905223078863fa13ef6363ab1d3486f3b5ae62a51712a08adfea53de")
        self.assertEqual(result["normalized_paragraphs_sha256"],
                         "dab0b688073dd00247f30129aba8c1cf6892c01124fe73abd7cbbf4ee2286c1f")
        self.assertEqual(result["corrected_publication_paragraphs_sha256"],
                         "8ca8777757918d46801cef3cb2bf4fab155f75fba5d3968a3e0369a2951dc51f")

    def reject_html_mutation(self, relative, mutate):
        target = proof.ROOT / relative
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            data = original_read(path, *args, **kwargs)
            if path == target:
                changed = mutate(data)
                self.assertNotEqual(data, changed, "tampering fixture must change HTML")
                return changed
            return data
        with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
            proof.verify()

    def test_reverted_or_partial_short_u_correction_rejected(self):
        for indices in ([614, 615, 620, 622, 624], [614], [615], [620], [622], [624]):
            with self.subTest(reverted=indices):
                def revert(source):
                    for index in indices:
                        original = proof.PUBLICATION_CORRECTIONS[index]
                        source = source.replace(original.replace("╝", "ў", 1), original, 1)
                    return source
                self.reject_html_mutation("proza/pereborsh/glava-27/index.html", revert)

    def test_unrelated_edits_in_corrected_blocks_rejected(self):
        for index, original in proof.PUBLICATION_CORRECTIONS.items():
            corrected = original.replace("╝", "ў", 1)
            for changed in (corrected + "!", corrected + " ", corrected.replace("i", "і", 1)):
                with self.subTest(index=index, changed=changed):
                    self.reject_html_mutation("proza/pereborsh/glava-27/index.html",
                        lambda s: s.replace(corrected, changed, 1))

    def test_unrelated_song_block_edit_rejected(self):
        for changed in ("серафімскія.", "серафiмскiя. ", "серафiмскiя.╝"):
            with self.subTest(changed=changed):
                self.reject_html_mutation("proza/pereborsh/glava-27/index.html",
                                          lambda s: s.replace("серафiмскiя.", changed, 1))

    def test_correction_requires_exact_original_source_block(self):
        for index, original in proof.PUBLICATION_CORRECTIONS.items():
            for changed in (original.replace("╝", "ў", 1), original + " ", original + "╝"):
                with self.subTest(index=index, changed=changed):
                    paragraphs = [""] * 738
                    for i, text in proof.PUBLICATION_CORRECTIONS.items():
                        paragraphs[i] = text
                    paragraphs[index] = changed
                    with self.assertRaisesRegex(ValueError, f"correction source text mismatch at paragraph {index}"):
                        proof.publication_paragraphs(paragraphs)

    def test_missing_private_zip_blocks_proof(self):
        with patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(proof.SourceUnavailable, "missing source ZIP"):
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
