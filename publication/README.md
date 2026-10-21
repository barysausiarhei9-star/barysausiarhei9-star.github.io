# Local publication catalog (M2.2)

`catalog.json` is the single reviewed metadata source for `sitemap.xml`,
`api/agent-feed/v1.json` and `feed.xml`. The local generator has no deployment
integration. HTML and media remain independently authored source files.

The catalog was seeded directly from the verified M1 artifacts at commit
`28b0ff50e92c7ca2a3f216c2dc38770c244a5d43`. It preserves 59 ordered pages,
45 RSS items, 14 explicit RU/EN alternate groups and four linked resources.
Generated canonical bytes match those three M1 Git blobs, including all
metadata, classifications, resource links and ordering. Both existing PDF
copies remain untouched; only the PDF already linked by `/kniga/` is listed.

## Run locally

Python 3.10 or newer is required. Install the pinned validator in a local
virtual environment; no other direct dependency is required:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r publication/requirements.txt
.venv\Scripts\python.exe -B tools/generate_publication.py
.venv\Scripts\python.exe -B tools/generate_publication.py --check
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_generate_publication.py -v
```

Omitting a mode is identical to `--check`: validate all inputs, compare all
three outputs and exit without writing. Exit status is 0 for matching
outputs, 1 for invalid input or output drift, and 2 for invalid CLI arguments.
After reviewing an intentional catalog change, regenerate explicitly:

```powershell
.venv\Scripts\python.exe -B tools/generate_publication.py --write
git diff -- sitemap.xml api/agent-feed/v1.json feed.xml publication tools tests
```

Serialization uses UTF-8 without BOM, LF, fixed indentation and catalog order.
Git's Windows `core.autocrlf` can produce CRLF checkouts: check mode reports
that byte drift without writing. Explicit `--write` restores canonical LF.
Repeated writes with identical inputs are byte-identical; already matching
outputs are left untouched. The tests use temporary copies and read the
M1 Git objects; that commit must be available locally. No server is needed.

## Catalog contract and review

- `format_version` is integer `1`; `site_url` is the existing canonical
  origin, `https://schrodingercat.org`.
- `rss_channel` records the exact M1 `title`, `link`, `description` and
  Atom `self_url`. No dates, summaries or licenses are synthesized.
- `alternate_groups` is an ordered list of explicit objects with `ru` and
  `en` page paths. Members must exist, have the matching language, be disjoint
  across groups and have HTML link evidence. Group membership is a reviewed
  decision: a language-switch fallback alone never creates a group. In
  particular, the Russian book and English book placeholder are not a pair.
- `pages` is in sitemap/Agent Feed order. Each page records its slash-delimited
  `path`, exact decoded HTML `title`, document `language`, reviewed `page_type`,
  `text_availability`, boolean `rss`, and optional `resources`. RSS filters
  these pages in order and includes only explicitly enabled content pages.
- Page IDs and canonical URLs are derived from `site_url` plus `path`.
  Each resource retains its M1 Agent Feed fields (`id`, `url`, `language`,
  `content_type`, `title`); its ID must equal its URL. No media becomes an
  additional HTML entry. See the [Agent Feed contract](../api/agent-feed/README.md).

All public `index.html` routes must appear exactly once. The site-verification
HTML file is not an index route and is excluded. Unknown fields, duplicate
JSON keys, invalid paths, missing/escaping files, invalid schema data and
duplicate global IDs fail validation. Every page must have matching title,
language, balanced markup and a main element; declared canonicals must agree.
Main text is checked excluding the heading, navigation, scripts and back links.
PNG resources require a PNG signature and matching image URL/alt text. The PDF
requires a PDF signature, typed HTML link and matching Book JSON-LD metadata.
The unchanged Draft 2020-12 Agent Feed schema validates the assembled feed
offline, with remote reference retrieval disabled.

Before any write, the entire catalog, referenced HTML/media, schema, generated
serializations and all three existing output paths must pass. A late invalid
page or resource cannot cause partial output changes. Writes then replace only
changed output bytes. This is a local operation, not a multi-file transaction:
an OS write failure or process interruption during writing may leave a subset
updated; fix the cause and rerun `--write`, then `--check`.

Classification, actual literary meaning, translation equivalence and poster
text still require human review. Checks verify structural evidence and metadata
agreement; they do not OCR images or infer classifications or translations.
When intentionally editing content, update and review the catalog explicitly,
regenerate, inspect the scoped diff and reassess the M1 regression expectations.
The existing Agent Feed schema, HTML, literary text, assets, both PDFs,
`llms.txt` and GitHub Pages workflow are outside the generator's write scope.
