# Agent Feed v1

Static UTF-8 JSON at `/api/agent-feed/v1.json`. Its JSON Schema (Draft
2020-12) is `/api/agent-feed/v1.schema.json`; the feed declares version
`1.0.0`. These ordinary files are included by the existing GitHub Pages
workflow, which uploads the repository root. No backend or build step is
required. Adding these files locally does not publish them.

## Contract and sources

- `entries` contains only the canonical public HTML URLs in `sitemap.xml`,
  once each, in sitemap order. The Google site-verification HTML file is
  not a content page and is excluded.
- `id` equals the full canonical URL, including its trailing slash. It is
  independent of entry order and title and stays stable while the URL stays
  stable. A moved page requires an explicit identity/migration decision.
- `canonical_url` comes from the sitemap; any HTML `rel="canonical"` must
  agree. Most existing pages do not declare that link.
- `language` is the page's `<html lang>` value. It describes the document,
  not every linked work or every text fragment within it. In particular,
  the English homepage also links to Russian works.
- `content_type` is `text/html` for every page. `title` is the decoded
  document `<title>`, preserving spelling, punctuation and site suffixes.
- `page_type` is `content` for populated works, about pages and the Russian
  book landing page; `section_index` for the two homepages, article indexes
  and three Russian poetry listing pages; or `placeholder` for a section
  with only a heading and no works.
- `text_availability` is `html_text` for populated HTML text or listings,
  `image_only` when the poem is present only in a linked poster image, and
  `heading_only` for placeholders. It describes the page's main content;
  navigation and back links do not count as work text. Book landing-page
  text does not mean the PDF's full text is embedded in HTML.
- Optional `resources` describes selected existing media linked or embedded
  by the page. Resource `id` equals its absolute `url`. It is not an HTML
  entry. The Russian PDF's title and language come from `/kniga/` (including
  its Book structured data); poster titles come from existing image `alt`
  attributes. Media types match the source declarations/file signatures.

The feed makes no translation relationships from language-switch links:
some links lead to section fallbacks rather than translations. It includes
no invented summaries, publication dates, licenses or AI training permissions.
Missing rights fields do not grant permission.

## Verified availability

| Language | Content | Section index | Placeholder | HTML total |
| --- | ---: | ---: | ---: | ---: |
| ru | 37 | 5 | 1 | 43 |
| en | 11 | 2 | 3 | 16 |
| Total | 48 | 7 | 4 | 59 |

The four placeholders are `/proza/`, `/en/prose/`, `/en/poetry/` and
`/en/book/`. There are no prose texts, English poems or English book
translation on those pages.

`/poeziya/endemik/`, `/poeziya/mad-national-idea/` and `/poeziya/obmanutye/`
are populated Russian poems: visual inspection confirms their text is in
the poster PNGs. They are `content` with `image_only` availability, not
placeholders. Their images are linked resources, without OCR transcription.

The original Russian book PDF is linked once under `/kniga/` at
`/assets/books/koshka-shredingera.pdf`. It is not a sixtieth HTML entry or
an English translation. In total there are four linked resources: one
Russian PDF and three Russian poem posters.

## Validation and maintenance

For an update, parse both JSON files and validate the feed against the
versioned schema. The schema checks shape, allowed values and availability
constraints. Also check these repository-level invariants, which JSON Schema
alone cannot enforce:

1. The entry URL set equals the sitemap URL set, with each URL present once.
2. IDs are globally unique across pages and resources and equal their URLs.
3. Every page route resolves to its existing `index.html`; title and language
   match the HTML, and declared canonical links agree with the sitemap.
4. Each media URL resolves to an existing file and occurs in its parent page;
   media type, title and language have source evidence.
5. Reinspect main content and images before changing availability or type;
   do not treat language-switch fallbacks as translated works.
6. Review the scoped diff and confirm existing files remain untouched.

Initial local validation passed all of these checks for 59 pages and four
resources, including a local HTTP JSON round-trip and schema-link resolution.
Production HTTP availability remains unverified until a separately authorized
publication. No commit, push or deployment is part of this change.

Keep v1 changes compatible with this contract. Breaking changes require a
new major-version feed and schema URL. Content inventory changes do not
imply a schema-version change; update the counts above when the site changes.
