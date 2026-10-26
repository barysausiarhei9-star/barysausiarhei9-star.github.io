"""Read-only, source-backed publication proof. The private ZIP is required locally."""

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "source-books/berezina_e_l--gthtjho.fb2.zip"
SOURCE_SHA256 = "95a60f7257a121fa323164eab30b78081ee50b99cc7ef72d300848ccb23315b7"
BASE = "/proza/pereborsh/"
# Reviewed boundaries: FB2 section/p offsets, zero-based; end is exclusive.
STARTS = (29, 69, 89, 95, 110, 123, 133, 146, 158, 184, 220, 252, 302,
          328, 339, 343, 348, 357, 367, 392, 419, 455, 472, 481, 532, 570, 584)
VERSE_RANGES = ((18, 26), (41, 45), (53, 61), (73, 77), (101, 109),
                (163, 165), (177, 181), (204, 216), (237, 241), (254, 270),
                (282, 284), (330, 336), (394, 398), (421, 429), (509, 531),
                (588, 599), (604, 630), (635, 672), (677, 685), (690, 698), (703, 721))
CLOSING_HEADINGS = {602: "try-yangaly", 633: "pro-kvarki", 675: "k-moemu-kotu",
                    688: "utopiya", 701: "v-kontse-tonnelya", 724: "konets-pervoy-chasti"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


class ReadingHTML(HTMLParser):
    """Read decoded literary blocks, including all text inside the article."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.block = None
        self.in_article = False
        self.links = []
        self.ids = []
        self.h1 = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "article":
            self.in_article = True
        if tag == "a":
            self.links.append(attrs)
        if tag == "h1":
            self.h1.append(attrs)
        if "data-fb2-p" in attrs:
            require(self.in_article and self.block is None, "misplaced literary block")
            self.block = {"index": int(attrs["data-fb2-p"]), "tag": tag,
                          "attrs": attrs, "text": "", "inline": []}
        elif self.block is not None:
            self.block["inline"].append(("start", tag))

    def handle_endtag(self, tag):
        if self.block is not None:
            if tag == self.block["tag"]:
                self.blocks.append(self.block)
                self.block = None
            else:
                self.block["inline"].append(("end", tag))
        if tag == "article":
            self.in_article = False

    def handle_data(self, text):
        if self.block is not None:
            self.block["text"] += text
        elif self.in_article:
            require(not text.strip(), "unmapped/invented text inside literary article")


def normalized(text):
    # Normalize whitespace only; punctuation, case and all other codepoints survive.
    return re.sub(r"\s+", " ", text).strip()


def digest(paragraphs):
    return hashlib.sha256(json.dumps(paragraphs, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def verify(root=ROOT):
    source = root / SOURCE
    require(source.is_file(), "missing source ZIP; text must not be reconstructed")
    require(hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256,
            "source ZIP differs from reviewed source")
    with ZipFile(source) as archive:
        require(archive.namelist() == ["gthtjho.fb2"], "unexpected ZIP inventory")
        fb2 = archive.read("gthtjho.fb2")
    document = ET.fromstring(fb2)
    bodies = document.findall("{*}body")
    require(len(bodies) == 1 and len(bodies[0]) == 2, "unexpected FB2 body structure")
    section = bodies[0].find("{*}section")
    require(len(section) == 738 and all(p.tag.endswith("}p") for p in section),
            "unexpected FB2 paragraph structure")
    paragraphs = ["".join(p.itertext()) for p in section]
    require(tuple(i for i, p in enumerate(paragraphs) if p.startswith("ГЛАВА ")) == STARTS,
            "chapter boundaries differ from reviewed source")
    require(paragraphs[357].startswith("ГЛАВА КИБЕРНАДЦАТАЯ.") and
            paragraphs[584] == "ГЛАВА МИНУС ПЕРВАЯ. ПОСТМОРТУМ", "unusual headings changed")
    entries = [("vstuplenie", "Вступление", 14, 29)] + [
        (f"glava-{n:02}", paragraphs[start], start,
         STARTS[n] if n < len(STARTS) else 733) for n, start in enumerate(STARTS, 1)]
    expected_indices = [*range(14, 733), 734]
    all_blocks = []
    parsed = {}
    for n, (slug, label, start, end) in enumerate(entries):
        path = BASE + slug + "/"
        page = ReadingHTML((root / path.lstrip("/") / "index.html").read_text(encoding="utf-8"))
        parsed[path] = page
        require(len(page.h1) == 1, path + ": expected one reading heading")
        expected = [*range(start, end), *([734] if n == len(entries) - 1 else [])]
        require([p["index"] for p in page.blocks] == expected, path + ": paragraph boundaries/order")
        if n:
            require(page.blocks[0]["tag"] == "h1" and page.blocks[0]["text"] == label,
                    path + ": chapter heading mismatch")
        for block in page.blocks:
            i = block["index"]
            require(block["text"] == paragraphs[i], f"{path}: exact text mismatch at paragraph {i}")
            if any(a <= i < b for a, b in VERSE_RANGES):
                require("verse-line" in block["attrs"].get("class", "").split(),
                        f"verse formatting lost at paragraph {i}")
            def inline_nodes(element):
                nodes = []
                for child in element:
                    tag = {"strong": "strong", "emphasis": "em", "underline": "u"}[
                        child.tag.rsplit("}", 1)[-1]]
                    nodes.extend([("start", tag), *inline_nodes(child), ("end", tag)])
                return nodes
            require(block["inline"] == inline_nodes(section[i]), f"inline formatting changed at {i}")
        require(sum(a.get("href") in (BASE, BASE + "#toc") for a in page.links) >= 2, path + ": missing TOC links")
        for rel, neighbor in (("prev", n - 1), ("next", n + 1)):
            links = [a["href"] for a in page.links if a.get("rel") == rel]
            target = BASE + entries[neighbor][0] + "/" if 0 <= neighbor < len(entries) else None
            require(links == ([target, target] if target else []), path + ": broken " + rel)
        all_blocks.extend(page.blocks)
    require([p["index"] for p in all_blocks] == expected_indices, "coverage/order mismatch")
    source_text = [paragraphs[i] for i in expected_indices]
    html_text = [p["text"] for p in all_blocks]
    require(source_text == html_text, "source/HTML paragraph sequence mismatch")
    require([normalized(p) for p in source_text] == [normalized(p) for p in html_text],
            "normalized source/HTML text differs")
    toc = ReadingHTML((root / "proza/pereborsh/index.html").read_text(encoding="utf-8"))
    parsed[BASE] = toc
    toc_chapters = [a["href"] for a in toc.links
                    if a.get("href", "").startswith(BASE) and "#" not in a["href"]
                    and a["href"] != BASE]
    require(toc_chapters == [BASE + e[0] + "/" for e in entries], "TOC incomplete or reordered")
    for i, anchor in CLOSING_HEADINGS.items():
        require(any(p["index"] == i and p["tag"] == "h2" and p["attrs"].get("id") == anchor
                    for p in all_blocks), "closing heading missing: " + anchor)
        require(any(a.get("href") == BASE + "glava-27/#" + anchor for a in toc.links),
                "closing passage missing from TOC: " + anchor)
    actual_pages = {"/" + p.parent.relative_to(root).as_posix() + "/"
                    for p in (root / "proza/pereborsh").glob("*/index.html")}
    require(actual_pages == set(parsed) - {BASE}, "unexpected reading-page inventory")
    for path, page in parsed.items():
        require(len(page.ids) == len(set(page.ids)), path + ": duplicate fragment ID")
        for a in page.links:
            href = a.get("href", "")
            require("source-books" not in href and not href.endswith((".zip", ".fb2")), "private source link")
            url = urlsplit(href)
            if url.scheme or not url.path.startswith("/"):
                continue
            target = root / url.path.lstrip("/")
            require((target / "index.html").is_file() if url.path.endswith("/") else target.is_file(),
                    path + ": broken local link " + href)
            if url.fragment:
                require(url.path in parsed and url.fragment in parsed[url.path].ids,
                        "missing fragment: " + href)
    proza = ReadingHTML((root / "proza/index.html").read_text(encoding="utf-8"))
    require(any(a.get("href") == BASE for a in proza.links), "prose index lacks novel link")
    catalog = json.loads((root / "publication/catalog.json").read_text(encoding="utf-8"))
    novel = [p for p in catalog["pages"] if p["path"].startswith(BASE)]
    require([p["path"] for p in novel] == [BASE, *[BASE + e[0] + "/" for e in entries]],
            "catalog inventory/order differs")
    require(all(p["language"] == "ru" and p["text_availability"] == "html_text" for p in novel),
            "novel catalog classifications differ")
    require(not subprocess.check_output(["git", "ls-files", "--", "source-books"], cwd=root),
            "private source tracked/staged")
    require(subprocess.run(["git", "check-ignore", "-q", "--", SOURCE], cwd=root).returncode == 0,
            "source ZIP is not excluded by Git")
    return {"reading_pages": len(entries), "novel_html_pages": len(parsed),
            "paragraphs": len(source_text), "nonblank_paragraphs": sum(bool(p.strip()) for p in source_text),
            "coverage_percent": 100, "raw_paragraphs_sha256": digest(source_text),
            "normalized_paragraphs_sha256": digest([normalized(p) for p in source_text]),
            "fb2_sha256": hashlib.sha256(fb2).hexdigest(), "zip_sha256": SOURCE_SHA256}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
        print("PASS: exact and normalized text, paragraph order, headings, verse, TOC, links, navigation, private source exclusion")
    except (ValueError, OSError, ET.ParseError) as error:
        raise SystemExit("FAIL: " + str(error))
