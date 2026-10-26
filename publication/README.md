# Local publication catalog (M2.2)

`catalog.json` is the single reviewed metadata source for `sitemap.xml`,
`api/agent-feed/v1.json`, `feed.xml`, `assets/search-index.json` and
`assets/search-index-en.json`. The Pages workflow checks these same five outputs
before artifact upload. HTML and media remain independently authored source files.

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
five outputs and exit without writing. Exit status is 0 for matching
outputs, 1 for invalid input, missing outputs or byte drift, and 2 for invalid CLI arguments.
After reviewing an intentional catalog change, regenerate explicitly:

```powershell
.venv\Scripts\python.exe -B tools/generate_publication.py --write
git diff -- sitemap.xml api/agent-feed/v1.json feed.xml assets/search-index.json assets/search-index-en.json publication tools tests .github/workflows/pages.yml
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
serializations and all five existing output paths must pass. A late invalid
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

## Work-level discovery metadata (A3.1)

The optional top-level `works` object extends catalog format version `1` without
changing any of the five generated outputs. Its exact fields are:

- `version`: integer `1` (not a boolean).
- `items`: a nonempty ordered array of objects with registered page `path`,
  `type` (`book`, `novel`, `poem`, or `article`), and optional `parts`.
- `excluded_content`: an array of registered content-page paths intentionally
  excluded from work discovery.

An item's path identifies one principal work. Titles, languages, canonical URLs
and resources remain in the existing page records. `alternate_groups` alone
supplies its language versions; fallback links do not create translations. A
translation group can belong to only one principal item. There is no separate
work registry, duplicated translation map, or numeric ordering field.

Array order is editorial display order within categories, shared by both future
interfaces. The planned category order is Books (`book`), Prose (`novel`), Poetry,
Articles. The initial 36 items cover one PDF book, Pereborsh, 24 poems in their
existing 10/10/4 catalog order, and ten articles in existing listing order. The
ten article translation groups yield 46 principal language versions. Display
order is preserved, not inferred from paths, titles, dates or JSON object keys.

Only book/novel items may have `parts`, a nonempty ordered array referencing
content pages. Pereborsh's index remains a `section_index`; its 28 parts are the
introduction and 27 chapters in existing TOC order. Primary parts must match the
principal's language. Translated parts must have matching parent versions, and
each parent must link to all its own-language part versions in metadata order.
Repeated links and fragments on links to the same part do not duplicate it.
Parts cannot also be roots, belong to multiple parents, or form nested cycles.
Poem/article roots must be content pages; book/novel index roots need registered
parts or their existing validated PDF resource.

Every content page must have exactly one role: principal language version, part
language version, or explicit exclusion. The three initial exclusions are
`/about/`, `/articles/about/`, and `/en/about/`. Other section indexes are not
implicitly works. New content requires an explicit classification when `works`
is present, even if it is already registered in `pages`. Unknown fields,
unsupported versions, invalid/unregistered paths, duplicate or conflicting roles,
missing coverage, and unsupported part links/order fail before any output writes.
Work boundaries, genre, exclusions and editorial display order still need review;
validation does not infer literary meaning.

An updated generator still accepts legacy catalogs with no `works` block and
preserves their existing publication behavior. Older generators reject the new
field, so metadata and validator changes must travel together. Malformed or
incomplete `works` metadata never falls back to legacy behavior. Existing HTML,
resource, schema, translation-evidence and public-route coverage checks remain.

A3.1 validates metadata only: it creates no `/works/` or `/en/works/` pages and
does not change the five-output write allowlist or deployment configuration.
Future rendering requires a separate implementation; it must use this same
catalog, explicitly register its output routes, and preserve read-only default
checks and fail-closed validation. No unregistered file is automatically published.

## Pages deployment gate

The existing Pages workflow installs the validator from
`publication/requirements.txt` and runs
`python -B tools/generate_publication.py --check` after checkout, before Pages
configuration and artifact upload. This is the same read-only local check:
invalid inputs or a stale, missing or corrupted output (including either search
index) fail the job, so artifact upload and deployment cannot proceed. CI never
regenerates outputs or commits changes. Validator setup or installation failures
also stop the job. Existing push-to-`main` and manual workflow triggers are unchanged;
the Operator controls generation, review, commits and pushes.

## Static full-text search

The same `--write` command rebuilds `assets/search-index.json` (Russian) and
`assets/search-index-en.json` (English); `--check`
detects stale text as well as publication metadata drift. The generator runs
offline, with no background job, OCR or PDF extraction. Keep both generated
indexes in the reviewed local publication diff after editing HTML.

To publish new RU or EN content, author its HTML and add its reviewed metadata
to the catalog, then run `--write`, review the five-output diff and run `--check`.
The matching language index updates automatically; the other index stays unchanged.
RSS inclusion still requires the page's explicit `rss: true` setting. Do not edit
search indexes manually. A missing output fails before any writes; restore it from
Git, then regenerate and check.

Each index includes only catalog `content` pages with its own language (`ru` or `en`), after
all existing HTML/resource/schema checks pass. Titles come from the verified
catalog. The current inventory is 65 Russian entries and 11 English entries.
Text comes only from visible main content, excluding primary headings already
represented by titles, navigation, back links, novel author labels, footers,
scripts, forms and artwork captions. Image-only works have searchable titles
and an empty body. Section listings and placeholders are omitted. Identical
normalized bodies in the same language appear once, with the first sorted
path retained. Both existing about pages contain distinct text and are included. Output uses sorted
paths, UTF-8, LF, compact JSON and no timestamps. Existing literary HTML,
PDFs and images remain source files; search never rewrites them.

The Russian `/search/` interface matches Cyrillic without case distinctions,
treats `ё` like `е`, supports word fragments and quoted phrases, and requires
all query terms. Title matches rank first, followed by contiguous phrase
matches; canonical URL breaks ties. Snippets are limited to 220 source
characters plus ellipses and rendered using text nodes. There is no stemming,
typo correction or translation. The index is fetched
once on the first query; searching then runs locally in the browser.

The English `/en/search/` interface shares the same search logic and styles,
with English status messages and its separate index. Both search routes appear
in the sitemap and Agent Feed as section indexes, and are excluded from RSS
and searchable content. English navigation links to `/en/search/` throughout.

Focused checks (Node 18+ for the browser search functions):

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_search_index.py -v
node --test tests/search.test.cjs
```

With an existing Playwright installation available to Node (for example via
`NODE_PATH`), run `node tests/search.browser.cjs` for local Chromium checks at
1280, 768, 375 and 320 px. It serves only local files, checks canonical links,
empty states, escaping and fetch recovery, and saves desktop/mobile screenshots
in the system temporary directory. No dependency is added to the published site.
