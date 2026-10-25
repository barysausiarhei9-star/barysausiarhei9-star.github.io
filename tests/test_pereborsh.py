"""Source-backed integrity and tampering checks; private local source is not committed."""

from pathlib import Path
import re
import unittest
from unittest.mock import patch

from tools import verify_pereborsh as proof


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
