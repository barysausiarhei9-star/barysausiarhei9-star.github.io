"""Extract searchable HTML text after publication validation; no OCR or PDF parsing."""

import json
import re
from html.parser import HTMLParser


VOID = set("area base br col embed hr img input link meta param source track wbr".split())
BLOCK = set("article section div p h1 h2 h3 h4 h5 h6 li ul ol blockquote pre br hr table tr td".split())
EXCLUDED = set("header footer nav script style template noscript form button figure figcaption h1".split())


class SearchText(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        excluded = (tag in EXCLUDED or "hidden" in attrs or
                    attrs.get("aria-hidden") == "true" or
                    bool(set(attrs.get("class", "").split()) & {"back", "book-author"}))
        if tag in BLOCK:
            self.parts.append(" ")
        if tag not in VOID:
            self.stack.append((tag, excluded))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        self.stack.pop()
        if tag in BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if any(tag == "main" for tag, _ in self.stack) and not any(x for _, x in self.stack):
            self.parts.append(data)

    @property
    def text(self):
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


def render_search(root, catalog, language="ru"):
    pages, seen = [], set()
    # Stable path order chooses a repeatable canonical result for identical bodies.
    for page in sorted(catalog["pages"], key=lambda p: p["path"]):
        if page["page_type"] != "content" or page["language"] != language:
            continue
        body = ""
        if page["text_availability"] == "html_text":
            body = SearchText((root / (page["path"].lstrip("/") + "index.html"))
                              .read_text(encoding="utf-8")).text
        key = (page["language"], body.casefold() if body else page["title"].casefold())
        if key in seen:
            continue
        seen.add(key)
        pages.append({"url": catalog["site_url"] + page["path"], "title": page["title"],
                      "language": page["language"], "text": body})
    return (json.dumps({"version": 1, "pages": pages}, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")
