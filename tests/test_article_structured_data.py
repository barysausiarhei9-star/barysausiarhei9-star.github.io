"""P2.1: verify authored Article metadata against publication and HTML evidence."""

import json
import unittest

from tools import generate_publication as generator


class ArticleHTML(generator.PageHTML):
    def __init__(self, source):
        self.heading = []
        super().__init__(source)

    def handle_data(self, data):
        super().handle_data(data)
        if any(tag == "h1" for tag, _ in self.stack):
            self.heading.append(data)


class ArticleStructuredDataTests(unittest.TestCase):
    def test_all_article_pairs_have_localized_verified_metadata(self):
        catalog = generator.load_json(generator.ROOT / "publication/catalog.json")
        pages = {page["path"]: page for page in catalog["pages"]}
        articles = [work for work in catalog["works"]["items"] if work["type"] == "article"]
        self.assertEqual(len(articles), 27)
        names = {"ru": "Елена Березина", "en": "Elena Berezina"}
        site_names = {"ru": "Кошка Шрёдингера", "en": "Schrödinger’s Cat"}
        visited = set()
        for article in articles:
            groups = [group for group in catalog["alternate_groups"]
                      if article["path"] in group.values()]
            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(set(group), {"ru", "en"})
            for language, route in group.items():
                with self.subTest(route=route):
                    self.assertNotIn(route, visited)
                    visited.add(route)
                    page = pages[route]
                    self.assertEqual(page["language"], language)
                    source = (generator.ROOT / route.lstrip("/") / "index.html").read_text(
                        encoding="utf-8")
                    html = ArticleHTML(source)
                    self.assertEqual(html.matching("html")[0]["lang"], language)
                    self.assertEqual("".join(html.title), page["title"])
                    self.assertEqual(len(html.matching("h1")), 1)
                    headline = " ".join("".join(html.heading).split())
                    self.assertIn(headline.casefold(), page["title"].casefold())
                    meta = {attrs.get("property"): attrs.get("content")
                            for attrs in html.matching("meta")}
                    self.assertEqual(headline, meta["og:title"])
                    self.assertEqual(site_names[language], meta["og:site_name"])
                    canonical = catalog["site_url"] + route
                    self.assertEqual([link["href"] for link in html.matching("link")
                                      if link.get("rel") == "canonical"], [canonical])
                    self.assertEqual(meta["og:url"], canonical)
                    for lang, alternate in group.items():
                        self.assertTrue(any(link.get("hreflang") == lang and
                                            link.get("href") in (
                                                alternate, catalog["site_url"] + alternate)
                                            for link in html.matching("link") + html.matching("a")))
                    self.assertEqual(len(html.scripts), 1)
                    data = json.loads("".join(html.scripts[0]),
                                      object_pairs_hook=generator.unique_object,
                                      parse_constant=lambda value: self.fail(value))
                    other = "en" if language == "ru" else "ru"
                    # Exact fields also exclude unverified dates, images and author IDs.
                    self.assertEqual(data, {
                        "@context": "https://schema.org",
                        "@type": "Article",
                        "headline": headline,
                        "author": {"@type": "Person", "name": names[language],
                                   "alternateName": names[other]},
                        "url": canonical,
                        "inLanguage": language,
                        "isPartOf": {"@type": "WebSite", "name": site_names[language],
                                     "url": catalog["site_url"] + "/"},
                    })
                    # The non-rendering data block belongs in the document head.
                    head = source.split("</head>", 1)[0]
                    self.assertIn('<script type="application/ld+json">', head)
        self.assertEqual(len(visited), 54)


if __name__ == "__main__":
    unittest.main()
