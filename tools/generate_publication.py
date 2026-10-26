"""Validate reviewed publication metadata; write only with explicit --write."""

import argparse
import json
import re
import sys
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ("sitemap.xml", "api/agent-feed/v1.json", "feed.xml", "assets/search-index.json",
           "assets/search-index-en.json")
WORK_ROUTES = {"ru": "/works/", "en": "/en/works/"}
WORK_OUTPUTS = tuple(path.lstrip("/") + "index.html" for path in WORK_ROUTES.values())
NAV_START = b"<!-- site-nav:start -->"
NAV_END = b"<!-- site-nav:end -->"
SITE = "https://schrodingercat.org"
SCHEMA_URL = SITE + "/api/agent-feed/v1.schema.json"
VOID = set("area base br col embed hr img input link meta param source track wbr".split())


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), "expected an object")
    require(set(required) <= value.keys() <= set(required) | set(optional),
            "missing or unknown fields: " + repr(list(value)))


def text(value):
    require(isinstance(value, str) and value.strip(), "expected nonempty text")
    require(all(c in "\t\n\r" or ord(c) >= 32 for c in value), "invalid text control character")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: require(False, "invalid JSON constant: " + value))


def page_path(value):
    require(isinstance(value, str) and re.fullmatch(r"/(?:[a-z0-9-]+/)*", value),
            "invalid page path: " + repr(value))
    return value


def local_file(root, relative):
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()), "file escapes repository: " + relative)
    require(path.is_file(), "missing file: " + relative)
    return path


class PageHTML(HTMLParser):
    """Inspect existing HTML evidence, without deriving publication metadata."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tags = []
        self.title = []
        self.body_text = []
        self.scripts = []
        self.script = None
        self.feed(source)
        self.close()
        require(not self.stack, "unclosed HTML tags")

    def handle_starttag(self, tag, attrs):
        require(len(dict(attrs)) == len(attrs), "duplicate HTML attribute")
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "script":
            self.script = []
            if attrs.get("type") == "application/ld+json":
                self.scripts.append(self.script)
        if tag not in VOID:
            self.stack.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        require(self.stack and self.stack[-1][0] == tag, "unbalanced HTML tag: " + tag)
        self.stack.pop()
        if tag == "script":
            self.script = None

    def handle_data(self, data):
        names = [tag for tag, _ in self.stack]
        if "title" in names:
            self.title.append(data)
        if self.script is not None:
            self.script.append(data)
        excluded = any(tag in {"h1", "script", "style", "nav"} or
                       (tag == "a" and "back" in attrs.get("class", "").split())
                       for tag, attrs in self.stack)
        if "main" in names and not excluded:
            self.body_text.append(data)

    def matching(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


def validate_html(root, page, source=None):
    html = PageHTML(source if source is not None else
                    local_file(root, page["path"].lstrip("/") + "index.html").read_text(encoding="utf-8"))
    require(len(html.matching("html")) == 1 and
            html.matching("html")[0].get("lang") == page["language"],
            "HTML language mismatch: " + page["path"])
    require(len(html.matching("title")) == 1 and "".join(html.title) == page["title"],
            "HTML title mismatch: " + page["path"])
    require(len(html.matching("main")) == 1, "missing main content: " + page["path"])
    if page["text_availability"] == "heading_only":
        require(html.matching("h1"), "placeholder heading missing: " + page["path"])
    require(not html.matching("base"), "HTML base URL is unsupported")
    for link in html.matching("link"):
        if "canonical" in link.get("rel", "").split():
            require(link.get("href") == SITE + page["path"], "HTML canonical mismatch")
    has_text = bool("".join(html.body_text).strip())
    require(has_text == (page["text_availability"] == "html_text"),
            "main text availability mismatch: " + page["path"])
    return html


def validate_resource(root, page, resource, html):
    require(resource["id"] == resource["url"], "resource ID must equal URL")
    relative = resource["url"].removeprefix(SITE + "/")
    require(resource["url"].startswith(SITE + "/assets/") and
            re.fullmatch(r"assets/[a-z0-9/-]+\.(pdf|png)", relative), "invalid resource URL")
    file = local_file(root, relative)
    require(resource["language"] == page["language"], "resource language mismatch")
    if resource["content_type"] == "image/png":
        with file.open("rb") as stream:
            require(stream.read(8) == b"\x89PNG\r\n\x1a\n", "invalid PNG signature")
        require(relative.endswith(".png"), "PNG extension mismatch")
        require(any(urljoin(SITE + page["path"], img.get("src", "")) == resource["url"]
                    and img.get("alt") == resource["title"] for img in html.matching("img")),
                "PNG link/alt mismatch")
    else:
        with file.open("rb") as stream:
            require(stream.read(5) == b"%PDF-", "invalid PDF signature")
        require(relative.endswith(".pdf"), "PDF extension mismatch")
        require(any(urljoin(SITE + page["path"], a.get("href", "")) == resource["url"]
                    and a.get("type") == "application/pdf" for a in html.matching("a")),
                "missing typed PDF link")
        books = [json.loads("".join(script), object_pairs_hook=unique_object)
                 for script in html.scripts]
        require(any(book.get("@type") == "Book" and book.get("name") == resource["title"]
                    and book.get("inLanguage") == resource["language"]
                    and book.get("encoding", {}).get("contentUrl") == resource["url"]
                    and book.get("encoding", {}).get("encodingFormat") == "application/pdf"
                    for book in books), "PDF Book metadata mismatch")


def validate_works(catalog, html_pages, alternates):
    """Validate optional discovery metadata without changing publication outputs."""
    if "works" not in catalog:
        return
    works = catalog["works"]
    fields(works, ("version", "items", "excluded_content"))
    require(type(works["version"]) is int and works["version"] == 1,
            "unsupported works version")
    require(isinstance(works["items"], list) and works["items"],
            "works items must be a nonempty ordered array")
    require(isinstance(works["excluded_content"], list), "excluded_content must be an array")
    pages = {p["path"]: p for p in catalog["pages"]}
    roles = {}

    def reference(value):
        page_path(value)
        require(value in pages, "unregistered works reference: " + value)
        require(value not in WORK_ROUTES.values(), "discovery page cannot be a work reference")
        return value

    def versions(value):
        return list(alternates[value].values()) if value in alternates else [value]

    def claim(value, role):
        require(value not in roles, "duplicate/conflicting works role: " + value)
        roles[value] = role

    # Claim every principal version first, so parts can never be other roots,
    # their translations, or members of a cycle, regardless of item order.
    for work in works["items"]:
        fields(work, ("path", "type"), ("parts",))
        principal = reference(work["path"])
        require(work["type"] in ("book", "novel", "poem", "article"), "invalid work type")
        if "parts" in work:
            require(work["type"] in ("book", "novel") and
                    isinstance(work["parts"], list) and work["parts"],
                    "parts require a book/novel and a nonempty ordered array")
        for variant in versions(principal):
            page = pages[variant]
            require(page["page_type"] in ("content", "section_index"),
                    "invalid principal page classification: " + variant)
            if work["type"] in ("poem", "article"):
                require(page["page_type"] == "content", "poem/article must be content: " + variant)
            elif page["page_type"] == "section_index":
                require(work.get("parts") or any(r["content_type"] == "application/pdf"
                        for r in page.get("resources", [])),
                        "book/novel index lacks parts or PDF: " + variant)
            claim(variant, "principal")

    for work in works["items"]:
        principal = work["path"]
        parts = work.get("parts", [])
        parent_languages = {pages[p]["language"] for p in versions(principal)}
        for part in parts:
            reference(part)
            require(pages[part]["language"] == pages[principal]["language"],
                    "primary part language differs from principal: " + part)
            for variant in versions(part):
                require(pages[variant]["page_type"] == "content", "part must be content: " + variant)
                require(pages[variant]["language"] in parent_languages,
                        "part language has no parent version: " + variant)
                claim(variant, "part")
        # Match each parent's language to its ordered part versions. Fallback
        # links never establish a translation or a parent/child relationship.
        for parent in versions(principal):
            expected = []
            for part in parts:
                matches = [p for p in versions(part)
                           if pages[p]["language"] == pages[parent]["language"]]
                require(len(matches) == 1, "part has no matching parent-language version: " + part)
                expected.append(SITE + matches[0])
            expected_set = set(expected)
            actual = []
            for link in html_pages[parent].matching("a"):
                target = urljoin(SITE + parent, link.get("href", "")).split("#", 1)[0]
                if target in expected_set and target not in actual:
                    actual.append(target)
            require(actual == expected, "parts links/order disagree with parent: " + parent)

    for excluded in works["excluded_content"]:
        reference(excluded)
        require(pages[excluded]["page_type"] == "content", "excluded page must be content: " + excluded)
        claim(excluded, "excluded")
    missing = [p for p, page in pages.items() if page["page_type"] == "content" and p not in roles]
    require(not missing, "unclassified content pages: " + repr(missing))


def validate_navigation(catalog):
    """Validate the optional contract; page migration remains inactive in A3.3.1."""
    if "navigation" not in catalog:
        return
    navigation = catalog["navigation"]
    fields(navigation, ("version", "aria_label", "items"))
    require(type(navigation["version"]) is int and navigation["version"] == 1,
            "unsupported navigation version")
    fields(navigation["aria_label"], ("ru", "en"))
    require(isinstance(navigation["items"], list) and navigation["items"],
            "navigation items must be a nonempty ordered array")
    pages = {p["path"]: p for p in catalog["pages"]}
    ids, targets = set(), {"ru": set(), "en": set()}

    def label(value):
        text(value)
        require(value == value.strip() and len(value.splitlines()) == 1 and
                not any(c in "\r\n\t\x7f" for c in value),
                "navigation labels must be trimmed single-line text")

    def reference(value, language):
        page_path(value)
        require(value in pages and pages[value]["language"] == language,
                "navigation target must be registered in its language: " + value)

    for value in navigation["aria_label"].values():
        label(value)
    for item in navigation["items"]:
        fields(item, ("id", "labels", "targets", "match"), ("active_pages",))
        require(isinstance(item["id"], str) and re.fullmatch(r"[a-z][a-z0-9-]*", item["id"]),
                "invalid navigation item ID")
        require(item["id"] not in ids, "duplicate navigation item ID")
        ids.add(item["id"])
        fields(item["labels"], ("ru", "en"))
        fields(item["targets"], ("ru", "en"))
        require(item["match"] in ("exact", "section"), "invalid navigation match mode")
        for language in ("ru", "en"):
            label(item["labels"][language])
            target = item["targets"][language]
            reference(target, language)
            require(target not in targets[language], "duplicate navigation target: " + target)
            targets[language].add(target)
            require(item["match"] != "section" or target not in ("/", "/en/"),
                    "language home must use exact navigation matching")

    exceptions = {"ru": set(), "en": set()}
    for item in navigation["items"]:
        if "active_pages" not in item:
            continue
        fields(item["active_pages"], ("ru", "en"))
        for language, paths in item["active_pages"].items():
            require(isinstance(paths, list), "navigation active_pages must be arrays")
            for path in paths:
                reference(path, language)
                require(path not in targets[language], "active exception shadows a menu destination")
                require(path not in exceptions[language], "duplicate navigation active-page exception")
                exceptions[language].add(path)


def render_navigation(catalog, path):
    """Pure shared renderer, deliberately not called by publication rendering yet."""
    validate_navigation(catalog)
    require("navigation" in catalog, "navigation rendering requires navigation metadata")
    page_path(path)
    pages = {p["path"]: p for p in catalog["pages"]}
    require(path in pages, "unregistered navigation context: " + path)
    language = pages[path]["language"]
    require(language in ("ru", "en"), "unsupported navigation language")
    navigation = catalog["navigation"]
    items = navigation["items"]
    selected = next((item for item in items
                     if path in item.get("active_pages", {}).get(language, [])), None)
    if selected is None:
        selected = next((item for item in items if item["targets"][language] == path), None)
    if selected is None:
        candidates = [item for item in items if item["match"] == "section"
                      and path.startswith(item["targets"][language])]
        selected = max(candidates, key=lambda item: len(item["targets"][language]), default=None)
    lines = ['<nav class="site-nav" aria-label="' + escape(navigation["aria_label"][language]) + '">']
    for item in items:
        target = item["targets"][language]
        current = ''
        if item is selected:
            current = ' aria-current="' + ('page' if target == path else 'location') + '"'
        lines.append(f'  <a href="{escape(target)}"{current}>{escape(item["labels"][language])}</a>')
    lines.append('</nav>')
    return ("\n".join(lines) + "\n").encode("utf-8")


class _NavigationMarkup(PageHTML):
    """Owned markup is one named nav with direct, text-only anchors."""

    def __init__(self, source):
        self.labels = []
        super().__init__(source)

    def handle_starttag(self, tag, attrs):
        require((tag == "nav" and not self.stack) or
                (tag == "a" and self.stack and self.stack[-1][0] == "nav"),
                "owned navigation may contain only one nav and direct anchors")
        if tag == "a":
            self.labels.append("")
        super().handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] == "a":
            self.labels[-1] += data
        else:
            require(not data.strip(), "text outside owned navigation anchors")

    def handle_comment(self, data):
        raise Invalid("comments inside owned navigation markup")

    def handle_decl(self, decl):
        raise Invalid("declarations inside owned navigation markup")

    def unknown_decl(self, data):
        raise Invalid("unknown declarations inside owned navigation markup")

    def handle_pi(self, data):
        raise Invalid("processing instructions inside owned navigation markup")


def _validate_navigation_markup(source):
    html = _NavigationMarkup(source)
    navs = html.matching("nav")
    require(len(navs) == 1, "owned region must contain exactly one navigation")
    fields(navs[0], ("class", "aria-label"))
    require(navs[0]["class"] == "site-nav", "owned region must contain site-nav")
    text(navs[0]["aria-label"])
    links = html.matching("a")
    require(links and all(s.strip() for s in html.labels), "owned navigation requires named links")
    targets = set()
    for link in links:
        fields(link, ("href",), ("aria-current",))
        page_path(link["href"])
        require(link["href"] not in targets, "duplicate owned navigation link")
        targets.add(link["href"])
        require("aria-current" not in link or link["aria-current"] in ("page", "location"),
                "invalid owned navigation active state")
    require(sum("aria-current" in a for a in links) <= 1, "multiple owned navigation active states")


class _NavigationRegionHTML(PageHTML):
    def __init__(self, source):
        self.boundaries = []
        super().__init__(source)

    def handle_comment(self, data):
        if data not in (" site-nav:start ", " site-nav:end "):
            return
        tags = [tag for tag, _ in self.stack]
        require("header" in tags and not any(t in tags for t in ("nav", "main", "script", "style", "template", "noscript")),
                "owned navigation markers must be in the header outside navigation")
        self.boundaries.append((data, self.stack.copy()))


def replace_navigation_region(source, replacement):
    """Pure byte splice; never discovers regions, serializes a page, or writes files."""
    require(isinstance(source, bytes) and isinstance(replacement, bytes), "navigation replacement requires bytes")
    require(source.count(NAV_START) == 1 and source.count(NAV_END) == 1,
            "expected exactly one owned navigation marker pair")
    begin = source.index(NAV_START) + len(NAV_START)
    end = source.index(NAV_END)
    require(begin <= end, "reversed owned navigation markers")
    document = _NavigationRegionHTML(source.decode("utf-8"))
    require(len(document.boundaries) == 2 and
            [b[0] for b in document.boundaries] == [" site-nav:start ", " site-nav:end "] and
            document.boundaries[0][1] == document.boundaries[1][1],
            "owned navigation markers must be real comments in the same header context")
    require(sum("site-nav" in a.get("class", "").split() for a in document.matching("nav")) == 1,
            "page must contain exactly one primary navigation")
    _validate_navigation_markup(source[begin:end].decode("utf-8"))
    require(replacement.endswith(b"\n") and b"\r" not in replacement,
            "replacement must use canonical LF with a final newline")
    _validate_navigation_markup(replacement.decode("utf-8"))
    return source[:begin] + b"\n" + replacement + source[end:]


def registered_work_routes(catalog):
    """Only the explicitly registered RU/EN pair enables generated HTML."""
    pages = {p["path"]: p for p in catalog["pages"]}
    registered = set(WORK_ROUTES.values()) & pages.keys()
    if not registered:
        return set()
    require(registered == set(WORK_ROUTES.values()), "register both works catalog routes")
    require("works" in catalog, "registered works catalogs require works metadata")
    require(isinstance(catalog["alternate_groups"], list), "alternate_groups must be an array")
    require(WORK_ROUTES in catalog["alternate_groups"], "works catalogs require their explicit RU/EN group")
    for language, path in WORK_ROUTES.items():
        page = pages[path]
        require(page["language"] == language and page["page_type"] == "section_index"
                and page["text_availability"] == "html_text" and page["rss"] is False
                and "resources" not in page, "invalid works catalog registration: " + path)
    return registered


def render_work_pages(catalog, alternates):
    """Render only validated metadata; never read listings from generated HTML."""
    if not registered_work_routes(catalog):
        return {}
    pages = {p["path"]: p for p in catalog["pages"]}
    output = {}
    for language, route in WORK_ROUTES.items():
        ru = language == "ru"
        brand = "Кошка Шрёдингера" if ru else "Schrödinger’s Cat"
        heading = "Все произведения" if ru else "All works"
        categories = (("book", "books", "Книги" if ru else "Books"),
                      ("novel", "prose", "Проза" if ru else "Prose"),
                      ("poem", "poetry", "Поэзия" if ru else "Poetry"),
                      ("article", "articles", "Статьи" if ru else "Articles"))
        navigation = (("/", "Главная"), ("/articles/", "Статьи"), ("/kniga/", "Книга"),
                      ("/proza/", "Проза"), ("/poeziya/", "Поэзия"), ("/about/", "О проекте"),
                      ("/search/", "Поиск")) if ru else (
                      ("/en/", "Home"), ("/en/articles/", "Articles"), ("/en/book/", "Book"),
                      ("/en/prose/", "Prose"), ("/en/poetry/", "Poetry"),
                      ("/en/about/", "About"), ("/en/search/", "Search"))
        lines = ['<!DOCTYPE html>', '<!-- Generated by tools/generate_publication.py; do not edit. -->',
                 f'<html lang="{language}">', '<head>', '  <meta charset="UTF-8" />',
                 '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
                 f'  <title>{escape(pages[route]["title"])}</title>',
                 f'  <link rel="canonical" href="{SITE + route}" />']
        lines.extend(f'  <link rel="alternate" hreflang="{lang}" href="{SITE + path}" />'
                     for lang, path in WORK_ROUTES.items())
        lines.extend(['  <link rel="stylesheet" href="/assets/style.css" />', '</head>',
                      '<body class="reading-page">', '  <header class="site-header">',
                      '    <div class="wrap header-row">', f'      <div class="wordmark">{brand}</div>',
                      '      <nav class="site-nav" aria-label="' +
                      ('Основная навигация' if ru else 'Main navigation') + '">'])
        lines.extend(f'        <a href="{path}">{label}</a>' for path, label in navigation)
        lines.extend([f'        <a href="{route}" aria-current="page">{heading}</a>', '      </nav>',
                      '      <div class="languages" aria-label="' + ('Язык' if ru else 'Language') + '">'])
        for lang, path in WORK_ROUTES.items():
            current = ' aria-current="page"' if lang == language else ''
            lines.append(f'        <a href="{path}" lang="{lang}" hreflang="{lang}"{current}>{lang.upper()}</a>')
        lines.extend(['      </div>', '    </div>', '  </header>', '  <main>',
                      '    <section class="hero-simple">', '      <div class="wrap">',
                      f'        <h1>{heading}</h1>', '        <p>' +
                      ('Всего произведений: ' if ru else 'Total works: ') +
                      str(len(catalog["works"]["items"])) + '</p>',
                      '        <nav class="pagination" aria-label="' +
                      ('Разделы каталога' if ru else 'Catalog sections') + '">'])
        lines.extend(f'          <a class="back" href="#{anchor}">{label}</a>'
                     for _, anchor, label in categories)
        lines.extend(['        </nav>', '      </div>', '    </section>',
                      '    <div class="content">', '      <div class="wrap">'])
        for kind, anchor, label in categories:
            lines.extend([f'      <section class="home-section" aria-labelledby="{anchor}">',
                          f'        <h2 class="section-heading" id="{anchor}">{label}</h2>'])
            for work in catalog["works"]["items"]:
                if work["type"] != kind:
                    continue
                variants = alternates.get(work["path"], {pages[work["path"]]["language"]: work["path"]})
                primary = variants.get(language, work["path"])
                page = pages[primary]
                lines.extend([f'        <div class="item" data-work-path="{work["path"]}">',
                              f'          <h3><a href="{primary}" lang="{page["language"]}" '
                              f'hreflang="{page["language"]}">{escape(page["title"])}</a></h3>'])
                if len(variants) == 2:
                    note = "Доступно на русском и английском." if ru else "Available in Russian and English."
                elif page["language"] == "ru":
                    note = ("На русском; английская версия на сайте отсутствует." if ru else
                            "Russian only. An English version is not available on this site.")
                else:
                    note = ("На английском; русская версия на сайте отсутствует." if ru else
                            "English only. A Russian version is not available on this site.")
                lines.append(f'          <p class="footer-note">{note}</p>')
                for lang, path in variants.items():
                    if path != primary:
                        label = (("Русская версия" if lang == "ru" else "Английская версия") if ru else
                                 ("Russian version" if lang == "ru" else "English version"))
                        lines.append(f'          <a class="back" data-translation="{lang}" '
                                     f'href="{path}" hreflang="{lang}">{label}</a>')
                lines.append('        </div>')
            lines.append('      </section>')
        lines.extend(['      </div>', '    </div>', '  </main>', '  <footer class="site-footer">',
                      f'    <div class="wrap">{brand}</div>', '  </footer>', '</body>', '</html>', ''])
        output[route.lstrip("/") + "index.html"] = "\n".join(lines).encode("utf-8")
    return output


def prepare(root):
    # Import on demand so a missing validator cannot silently skip validation.
    from jsonschema import Draft202012Validator
    from referencing import Registry

    catalog = load_json(root / "publication/catalog.json")
    fields(catalog, ("format_version", "site_url", "rss_channel", "alternate_groups", "pages"),
           ("works", "navigation"))
    require(type(catalog["format_version"]) is int and catalog["format_version"] == 1,
            "unsupported catalog format_version")
    require(catalog["site_url"] == SITE, "site_url must match existing Agent Feed contract")
    channel = catalog["rss_channel"]
    fields(channel, ("title", "link", "description", "self_url"))
    for value in channel.values():
        text(value)
    require(channel["link"] == SITE + "/" and channel["self_url"] == SITE + "/feed.xml",
            "RSS channel URLs mismatch")
    pages = catalog["pages"]
    require(isinstance(pages, list) and pages, "pages must be a nonempty ordered array")
    entries, paths, ids, html_pages = [], set(), set(), {}
    for page in pages:
        fields(page, ("path", "title", "language", "page_type", "text_availability", "rss"),
               ("resources",))
        path = page_path(page["path"])
        require(path not in paths, "duplicate page path: " + path)
        paths.add(path)
        require(type(page["rss"]) is bool, "rss must be boolean")
        require(not page["rss"] or page["page_type"] == "content", "RSS requires a content page")
        entry = {"id": SITE + path, "canonical_url": SITE + path,
                 "language": page["language"], "content_type": "text/html",
                 "title": page["title"], "page_type": page["page_type"],
                 "text_availability": page["text_availability"]}
        if "resources" in page:
            entry["resources"] = page["resources"]
        entries.append(entry)
    feed = {"$schema": SCHEMA_URL, "version": "1.0.0", "entries": entries}
    html_paths = set()
    for file in root.glob("**/index.html"):
        relative = file.relative_to(root)
        if not any(part.startswith(".") for part in relative.parts):
            html_paths.add("/" if relative.parent == Path(".")
                           else "/" + relative.parent.as_posix() + "/")
    generated_routes = registered_work_routes(catalog)
    require(paths - generated_routes == html_paths - generated_routes,
            "catalog must cover every existing public index.html route")
    schema = load_json(root / "api/agent-feed/v1.schema.json")
    Draft202012Validator.check_schema(schema)
    # Empty registry prohibits network resolution; the existing schema uses local refs only.
    Draft202012Validator(schema, registry=Registry()).validate(feed)
    for page, entry in zip(pages, entries):
        html = None if page["path"] in generated_routes else validate_html(root, page)
        if html is not None:
            html_pages[page["path"]] = html
        for item in [entry] + entry.get("resources", []):
            require(item["id"] not in ids, "duplicate global ID: " + item["id"])
            ids.add(item["id"])
            text(item["title"])
        for resource in entry.get("resources", []):
            validate_resource(root, page, resource, html)
        if page["text_availability"] == "image_only":
            require(any(r["content_type"] == "image/png" for r in page.get("resources", [])),
                    "image_only requires a linked PNG")
    groups = catalog["alternate_groups"]
    require(isinstance(groups, list), "alternate_groups must be an array")
    alternates = {}
    by_path = {p["path"]: p for p in pages}
    for group in groups:
        fields(group, ("ru", "en"))
        for language, path in group.items():
            page_path(path)
            require(path in by_path and by_path[path]["language"] == language,
                    "alternate target missing or language mismatch")
            require(path not in alternates, "overlapping alternate groups")
            alternates[path] = group
    validate_works(catalog, html_pages, alternates)
    validate_navigation(catalog)
    for name, data in render_work_pages(catalog, alternates).items():
        path = "/" + name.removesuffix("index.html")
        html_pages[path] = validate_html(root, by_path[path], data.decode("utf-8"))
    for path, group in alternates.items():
        for lang, target in group.items():
            require(any(a.get("hreflang") == lang and
                        urljoin(SITE + path, a.get("href", "")) == SITE + target
                        for a in html_pages[path].matching("a") + html_pages[path].matching("link")),
                    "alternate not supported by HTML: " + path)
    return catalog, feed, alternates


def xml_bytes(element):
    ET.indent(element, space="  ")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' +
            ET.tostring(element, encoding="unicode") + "\n").encode("utf-8")


def render(root=ROOT):
    if __package__:
        from .search_index import render_search
    else:
        from search_index import render_search
    catalog, feed, alternates = prepare(root)
    sitemap = ET.Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
                                    "xmlns:xhtml": "http://www.w3.org/1999/xhtml"})
    rss = ET.Element("rss", {"xmlns:atom": "http://www.w3.org/2005/Atom",
                             "xmlns:dc": "http://purl.org/dc/elements/1.1/", "version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    for key in ("title", "link", "description"):
        ET.SubElement(channel, key).text = catalog["rss_channel"][key]
    ET.SubElement(channel, "atom:link", {"href": catalog["rss_channel"]["self_url"],
                                       "rel": "self", "type": "application/rss+xml"})
    for page, entry in zip(catalog["pages"], feed["entries"]):
        url = ET.SubElement(sitemap, "url")
        ET.SubElement(url, "loc").text = entry["canonical_url"]
        group = alternates.get(page["path"], {})
        for lang in ("ru", "en"):
            if lang in group:
                ET.SubElement(url, "xhtml:link", {"rel": "alternate", "hreflang": lang,
                                                 "href": SITE + group[lang]})
        if page["rss"]:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = page["title"]
            ET.SubElement(item, "link").text = entry["canonical_url"]
            ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = entry["id"]
            ET.SubElement(item, "dc:language").text = page["language"]
    outputs = dict(zip(OUTPUTS[:3], (xml_bytes(sitemap),
                   (json.dumps(feed, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                   xml_bytes(rss))))
    # Detect serialization errors before touching any output.
    ET.fromstring(outputs["sitemap.xml"])
    ET.fromstring(outputs["feed.xml"])
    outputs["assets/search-index.json"] = render_search(root, catalog)
    outputs["assets/search-index-en.json"] = render_search(root, catalog, "en")
    outputs.update(render_work_pages(catalog, alternates))
    return outputs


def run(root=ROOT, write=False):
    outputs = render(root)
    targets = {name: local_file(root, name) for name in OUTPUTS}
    for name in outputs.keys() - targets.keys():
        require(name in WORK_OUTPUTS, "unauthorized generated output")
        target = root / name
        require(target.resolve() == root.resolve() / name, "generated output alias: " + name)
        require(not target.exists() or target.is_file(), "generated output is not a file: " + name)
        require(all(not p.exists() or p.is_dir() for p in target.parents),
                "generated output parent is not a directory: " + name)
        targets[name] = target
    different = [name for name, data in outputs.items()
                 if not targets[name].is_file() or targets[name].read_bytes() != data]
    if write:
        for name in different:
            if name in WORK_OUTPUTS:
                targets[name].parent.mkdir(parents=True, exist_ok=True)
            targets[name].write_bytes(outputs[name])
        print("PASS: validated; wrote " + str(len(different)) + " publication outputs")
        return 0
    if different:
        print("FAIL: publication outputs differ: " + ", ".join(different), file=sys.stderr)
        return 1
    print(f"PASS: catalog, HTML, resources and schema valid; all {len(outputs)} outputs match (read-only)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only validation (default)")
    mode.add_argument("--write", action="store_true", help="validate everything, then regenerate outputs")
    args = parser.parse_args()
    try:
        return run(write=args.write)
    except (ValueError, OSError, ImportError, ET.ParseError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    except Exception as error:
        # Includes jsonschema validation/ref-resolution failures; never proceed to writes.
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
