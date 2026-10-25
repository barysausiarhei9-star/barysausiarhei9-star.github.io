# Переборщ — publication inventory and local proof

Prepared from the supplied ZIP for the Russian `/proza/` section. No translation or cover was created.

- Repository: `barysausiarhei9-star/barysausiarhei9-star.github.io`, branch `main`, initial HEAD `f123a2ce6620fa85c2f652c04c506d1cb0958961`.
- Source: `source-books/berezina_e_l--gthtjho.fb2.zip`, member `gthtjho.fb2` (341,928 bytes).
- Source ZIP SHA-256: `95a60f7257a121fa323164eab30b78081ee50b99cc7ef72d300848ccb23315b7`.
- Extracted FB2 SHA-256: `9dc4c8aa8f70f0a288d36a5a8d4e324994c918c6fbebe204be991bff4b085e3a`.
- The ZIP remains unchanged. Extraction is local at `source-books/gthtjho.fb2`; `/source-books/` is ignored by Git, and neither source file is linked publicly or staged.

## Source interpretation

The FB2 contains one body, with a generated title and a single flat section of 738 `p` elements. Chapter boundaries are standalone `ГЛАВА ...` paragraphs, not XML sections. There are 27 chapters in the exact order below. File numbers indicate reading order; they do not replace the author’s chapter numbers.

The authorial reading sequence is section paragraphs **14–732, then 734**: 720 blocks, comprising 536 nonblank paragraphs and 184 blank paragraphs. Paragraph 734 preserves the original copyright line and its strong formatting. Exact comparison includes punctuation, NBSP, U+2028, internal newlines, unusual glyphs and repeated passages already present in the source.

The remaining 20 body paragraphs are converter/export material: the two generated body-title paragraphs; section paragraphs 0–6 (repeated author/title, origin, export dates, “Роман: Нет”, genre and separator); seven blank pre-title paragraphs 7–13; separator 733; and repeated export metadata 735–737. Author/title and “Автофикшен” are represented as page metadata. These export wrappers are outside the literary comparison; no narrative passage is omitted.

The introduction preserves `ПЕРЕБОРЩ`, `(Неоконченный роман для нативного интеллекта)`, the opening verse and `ЧАСТЬ ПЕРВАЯ`. “Вступление” is only a navigation label, outside the authorial article. The source ends with `КОНЕЦ ПЕРВОЙ ЧАСТИ`; no further part or ending is invented.

## Exact inventory

All routes below are relative to `/proza/pereborsh/`. Its `index.html` is the separate table of contents.

| Page | Exact source heading | FB2 section/p offsets (zero-based) |
| --- | --- | --- |
| `vstuplenie/` | Вступление (editorial navigation label) | 14–28 |
| `glava-01/` | ГЛАВА ПЕРВАЯ. "АВА" | 29–68 |
| `glava-02/` | ГЛАВА ВТОРАЯ. 'НЕЖЕЛАННАЯ' | 69–88 |
| `glava-03/` | ГЛАВА ТРЕТЬЯ. ПРАКТИКАНТКА. | 89–94 |
| `glava-04/` | ГЛАВА ЧЕТВЕРТАЯ. НЕУЛОВИМЫЙ ДЖО. | 95–109 |
| `glava-05/` | ГЛАВА ПЯТАЯ. В ОГОРОДЕ БУЗИНА | 110–122 |
| `glava-06/` | ГЛАВА ШЕСТАЯ. СОН, НАПРОЧУД ДЫВНЫЙ. | 123–132 |
| `glava-07/` | ГЛАВА СЕДЬМАЯ. ПУСТЬ КОМУ-ТО ПОВЕЗЛО... | 133–145 |
| `glava-08/` | ГЛАВА ВОСЬМАЯ. ЧИРГЁРЛЫ. | 146–157 |
| `glava-09/` | ГЛАВА ДЕВЯТАЯ. ХМУРАЯ СУТРА. | 158–183 |
| `glava-10/` | ГЛАВА ДЕСЯТАЯ. МАЛЬТУС ВСЕГДА ПРАВ. | 184–219 |
| `glava-11/` | ГЛАВА ОДИННАДЦАТАЯ. ДОРОГА В ПЕКЛО. | 220–251 |
| `glava-12/` | ГЛАВА ДВЕНАДЦАТАЯ. ПАНГОЛИНЫ, ГОВОРИШЬ? | 252–301 |
| `glava-13/` | ГЛАВА ТРИНАДЦАТАЯ. РЫДАЮТ ВСЕ. | 302–327 |
| `glava-14/` | ГЛАВА ЧЕТЫРНАДЦАТАЯ. ПАНДЕМОНИЧЕСКОЕ | 328–338 |
| `glava-15/` | ГЛАВА ПЯТНАДЦАТАЯ. КРЕАТИНОКРАТИЯ | 339–342 |
| `glava-16/` | ГЛАВА ШЕСТНАДЦАТАЯ. ТЩЕТА ФРАНКЕНШТЕЙНА. | 343–347 |
| `glava-17/` | ГЛАВА СЕМНАДЦАТАЯ. ДА УБОИТСЯ. | 348–356 |
| `glava-18/` | ГЛАВА КИБЕРНАДЦАТАЯ. ОТ УЛИЦКОЙ И РОЗОВА ДЛЯ ПЕТРОВЫХ И СИДОРОВЫХ. | 357–366 |
| `glava-19/` | ГЛАВА ВОСЕМНАДЦАТАЯ. МАГАТЭ НЕВМОГОТУ. | 367–391 |
| `glava-20/` | ГЛАВА ДЕВЯТНАДЦАТАЯ. ВИНОВАТАЯ Я | 392–418 |
| `glava-21/` | ГЛАВА ДВАДЦАТАЯ. ОТРИЦАНИЕ ОТРИЦАНИЯ | 419–454 |
| `glava-22/` | ГЛАВА ДВАДЦАТЬ ПЕРВАЯ. РАССКАЗ РЫСЯ. | 455–471 |
| `glava-23/` | ГЛАВА ДВАДЦАТЬ ВТОРАЯ. МИР, ГДЕ МОЖНО ПЕТЬ | 472–480 |
| `glava-24/` | ГЛАВА ДВАДЦАТЬ ТРЕТЬЯ. РЕШЕНИЕ НЕРЕШАЕМОГО | 481–531 |
| `glava-25/` | ГЛАВА ДВАДЦАТЬ ЧЕТВЕРТАЯ. АВА И ХРОМОЙ СИЛЬФИД. | 532–569 |
| `glava-26/` | ГЛАВА ДВАДЦАТЬ ПЯТАЯ. ПЕРО ИЗ ШЛЯПЫ И ШАХМАТЫ. | 570–583 |
| `glava-27/` | ГЛАВА МИНУС ПЕРВАЯ. ПОСТМОРТУМ | 584–732 + 734 |

The last reading page also preserves the untitled closing verse, all repeated “Закон Сохранения Странностей…” passages, and these source headings, linked individually from the contents:

- `ТРЫ ЯНГАЛЫ / (Беларуское)` — `glava-27/#try-yangaly`.
- `ПРО КВАРКИ` — `glava-27/#pro-kvarki`.
- `К моему коту` — `glava-27/#k-moemu-kotu`.
- `УТОПИЯ` — `glava-27/#utopiya`.
- `В КОНЦЕ ТОННЕЛЯ` — `glava-27/#v-kontse-tonnelya`.
- `КОНЕЦ ПЕРВОЙ ЧАСТИ` — `glava-27/#konets-pervoy-chasti`.

**HTML count:** 29 new novel pages = one contents page + one introduction + 27 chapters. The existing `/proza/index.html` is updated, so 30 HTML files are affected in total.

## Integrity and validation

The read-only proof is reproducible with the private ZIP present:

```powershell
.venv\Scripts\python.exe -B tools/verify_pereborsh.py
.venv\Scripts\python.exe -B tools/generate_publication.py --check
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_generate_publication.py -v
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_pereborsh.py -v
```

- PASS: **720/720 blocks, 100% coverage**, exact source/HTML paragraph text equality and original ordering. Each source offset occurs once. Source-authored repeats remain repeats.
- Exact paragraph-array SHA-256, identical for FB2 and HTML: `ea3e4b78905223078863fa13ef6363ab1d3486f3b5ae62a51712a08adfea53de`.
- Whitespace-normalized paragraph-array SHA-256, identical for FB2 and HTML: `dab0b688073dd00247f30129aba8c1cf6892c01124fe73abd7cbbf4ee2286c1f`.
- Hash serialization: UTF-8 JSON string array, `ensure_ascii=False`, compact separators `(',', ':')`; normalization replaces whitespace runs with a space and strips each paragraph. Exact comparison is stricter and runs first.
- PASS: chapter boundaries/headings, original inline formatting, verse lines, closing passages, complete contents, local links and fragments, two-way adjacent navigation and contents links at both ends of every reading page.
- PASS: local generator `--write` regenerated only `sitemap.xml`, `api/agent-feed/v1.json` and `feed.xml`; `--check` confirms canonical byte agreement, HTML/catalog agreement and schema validity. Inventory: **88 total pages, 73 RSS items**, including 29 new novel entries and 28 new RSS entries. Explicit alternate groups remain unchanged.
- PASS: all 15 publication tests. The M1 preservation test now compares all pre-existing entries after accounting only for the novel additions and the prose placeholder becoming a section.
- PASS: all 7 source-backed tests, including rejection of rewritten punctuation, omitted/duplicated/reordered paragraphs, invented text, broken navigation, lost verse formatting and incomplete contents. These tests skip when the intentionally private ZIP is absent; the standalone proof fails if it is absent.
- PASS: Chromium inspected 30 HTML pages at widths **320, 390, 768 and 1280 px** (120 page views), with no horizontal overflow, failed page/assets requests or script errors. Contents, previous/next and closing-fragment links were clicked successfully. Screenshots of the introduction, contents and longest chapter heading were inspected on mobile and desktop. After the contents list and multiline closing-heading layout were refined, 12 affected page views passed again.

## Files and decision

- New: `.gitignore`, `assets/pereborsh.css`, all 29 `/proza/pereborsh/**/index.html` files listed above, `tools/verify_pereborsh.py`, `tests/test_pereborsh.py`, this inventory.
- Updated: `proza/index.html`, `publication/catalog.json`, the three generated outputs, `tests/test_generate_publication.py`.
- English HTML, other works, shared CSS, artwork, images, PDFs, generator implementation and deployment configuration remain unchanged.
- Local-only ignored material: the original ZIP, extracted FB2, virtual environment and browser screenshots.

Result: **PASS**. No content or validation blockers. Safe to proceed: **yes**. Safe to commit the scoped publication changes: **yes**. No commit, push or deployment was performed. The next step is owner review of the contents and scoped diff before any separately authorized commit.
