"""Validate reviewed publication metadata; write only with explicit --write."""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ("sitemap.xml", "api/agent-feed/v1.json", "feed.xml", "assets/search-index.json")
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


def validate_html(root, page):
    html = PageHTML(local_file(root, page["path"].lstrip("/") + "index.html")
                    .read_text(encoding="utf-8"))
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


def prepare(root):
    # Import on demand so a missing validator cannot silently skip validation.
    from jsonschema import Draft202012Validator
    from referencing import Registry

    catalog = load_json(root / "publication/catalog.json")
    fields(catalog, ("format_version", "site_url", "rss_channel", "alternate_groups", "pages"))
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
    require(paths == html_paths, "catalog must cover every existing public index.html route")
    schema = load_json(root / "api/agent-feed/v1.schema.json")
    Draft202012Validator.check_schema(schema)
    # Empty registry prohibits network resolution; the existing schema uses local refs only.
    Draft202012Validator(schema, registry=Registry()).validate(feed)
    for page, entry in zip(pages, entries):
        html = validate_html(root, page)
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
    return outputs


def run(root=ROOT, write=False):
    outputs = render(root)
    targets = {name: local_file(root, name) for name in OUTPUTS}
    different = [name for name, data in outputs.items() if targets[name].read_bytes() != data]
    if write:
        for name in different:
            targets[name].write_bytes(outputs[name])
        print("PASS: validated; wrote " + str(len(different)) + " publication outputs")
        return 0
    if different:
        print("FAIL: publication outputs differ: " + ", ".join(different), file=sys.stderr)
        return 1
    print("PASS: catalog, HTML, resources and schema valid; all 4 outputs match (read-only)")
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
