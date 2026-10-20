# AGENTS.md — how to edit Apulainen.pro (for Codex, Claude and any AI agent)

Apulainen.pro is a static site (plain HTML + one CSS file) served by Cloudflare Workers from `public/`.
Company: Apulainen.pro, Ksm Service Oy, Y-tunnus 3528429-3. Site language: **Finnish only**.
Two owners edit it, each through their own AI agent: **sergei** (GitHub `kotelnikoff-sergei`) and **partner**.

## 1. Golden rules
1. **Only edit pages your owner owns.** Look the file up in `ownership.json` → `files`. If `owner` is not yours, stop and say so.
   Files not listed there are **shared** (design system, redirects, config, these instructions) — change them only in a
   separate PR that the other owner approves.
2. **Never change a URL.** File names = URLs (see §2). Renaming/moving/deleting a page needs a 301 line in `public/_redirects`
   (shared file). Every path in `migration/tilda-pages.json` must keep working.
3. **Keep the site `noindex`** (pilot): never remove `<meta name="robots" content="noindex, nofollow">`, `public/_headers`
   or `public/robots.txt` rules until both owners decide to launch.
4. **Design system only** (§4). No new colours, fonts, shadows or one-off inline styles for looks.
5. **Contacts:** WhatsApp first (`https://wa.me/358417232410`), then e-mail `apulainen.tilaus@gmail.com`.
   A phone number is never a button/call-to-action.
6. **Copy:** plain Finnish, no invented numbers, reviews or customer names. Prices: "alk." and incl. ALV 25,5 %.
7. **Do not run `migration/build_from_tilda.py`** — it rebuilds every page from the old Tilda export and would wipe all edits.
8. Work on a branch, open a PR, check the Cloudflare preview, then merge (§6).

## 2. From a URL to the file
Strip the domain (works the same for apulainen.pro and the `*.workers.dev` preview addresses):

| URL path | File |
|---|---|
| `/` | `public/index.html` (special, see §5) |
| `/muuttosiivous-vantaa` (no slash at the end) | `public/muuttosiivous-vantaa.html` |
| `/ikkunanpesu/helsinki` | `public/ikkunanpesu/helsinki.html` |
| `/ikkunanpesu/helsinki/kruununhaka/` (slash at the end) | `public/ikkunanpesu/helsinki/kruununhaka/index.html` |

Unsure? Search `ownership.json` for `"url": "/the-path"` — it gives the file and the owner.

## 3. Anatomy of a page (all pages except `/`)
```
<head>   title, meta description, canonical, og:*, JSON-LD  ← SEO, edit with care
<header class="top">  shared navigation               ← same on every page, do not edit per page
<main>
  <section class="hero"> breadcrumbs, the only <h1>, intro text, buttons
  <section class="blk"><div class="wrap"> … </div></section>   ← one per content block, edit freely
  …
  <section class="sec" id="yhteys"> contact block (WhatsApp + e-mail)
</main>
<footer class="foot">  shared footer                     ← do not edit per page
<script type="application/ld+json"> FAQPage (if the page has FAQ)
```
- Exactly **one `<h1>`** per page. Section titles `<h2 class="disp">`, card titles `<h3>`.
- `<title>` ≤ 60 characters, meta description ≤ 155. Keep `canonical` = `https://apulainen.pro` + the page path.
- If you change a FAQ question/answer, update the same text in the FAQPage JSON-LD at the bottom of the page.
- Internal links: relative paths only (`/hinnasto`, not `https://apulainen.pro/hinnasto`). The target must exist.

## 4. Design system (`public/assets/site.css`, shared)
Colours: background `#F4F5EF`, green `#2E6B45`, deep green `#1C3A27`, text `#17231A`, muted `#44544A`,
line `#DDE2D4`, mint `#E3EEDF`, yellow `#F2C14E` **only for offers/discounts**.
Fonts: Bricolage Grotesque (headings, class `disp`), Plus Jakarta Sans (text). Pages must work at **390 px** width.

Use only these building blocks (copy the HTML):
```html
<section class="blk"><div class="wrap">
  <div class="kicker">Pieni yläotsikko</div>
  <h2 class="disp">Osion otsikko</h2>
  <p>Leipäteksti.</p>
  <ul><li>Lista</li></ul>
  <div class="price">alk. 45 €/h</div>

  <div class="grid g3">                       <!-- g2 = 2 columns, g3 = 3 columns, stacks on mobile -->
    <div class="card"><img src="/images/x.webp" alt="Kuvaus" loading="lazy"><h3>Kortin otsikko</h3><p>Teksti</p></div>
  </div>

  <div class="gal"><img src="/images/a.webp" alt="…" loading="lazy"><img src="/images/b.webp" alt="…" loading="lazy"></div>
  <div class="gal one"><img src="/images/a.webp" alt="…" loading="lazy"></div>   <!-- one big image -->

  <ul class="links"><li><a href="/kotisiivous/espoo">Espoo</a></li></ul>         <!-- chips, e.g. districts -->

  <div class="tbl"><table><tr><td>Otsikko</td><td>Hinta</td></tr><tr><td>…</td><td>…</td></tr></table></div>

  <div class="faq"><details><summary>Kysymys?</summary><div class="ans">Vastaus.</div></details></div>

  <div class="acts">
    <a class="btn" href="https://wa.me/358417232410">Kirjoita WhatsAppiin</a>   <!-- main action -->
    <a class="btn ghost" href="/hinnasto">Katso hinnat</a>                       <!-- secondary -->
    <a class="btn yel" href="…">Tarjous</a>                                       <!-- offers only -->
  </div>
</div></section>
```
Need a new component or a CSS change? That is a **shared** change: separate PR touching `site.css`, approved by both.

Images: put new files in `public/images/` as `.webp`, max 1600 px wide, with a descriptive Finnish `alt`
and `loading="lazy"`. Adding new images is fine for both owners; replacing/deleting existing ones is shared.

## 5. The home page `/` (`public/index.html`, owner: partner)
A single file with its own inline CSS and a small script: sections `#etusivu`, `#ikkunat`, `#siivous` are shown by the URL
hash, and the price calculators use `data-act`, `data-v`, `data-size`, `data-freq` attributes and element ids
(`ikkunat-laskuri`, `siivous-laskuri`, `freq-box`, form field ids `w-*`, `k-*`). Keep those ids and data attributes,
or update the script at the bottom of the file in the same change.

## 6. Workflow (every change)
1. `git checkout main && git pull`, then `git checkout -b <owner>/<short-name>` (e.g. `partner/muuttosiivous-vantaa-hinnat`).
2. Find the file (§2), confirm the owner in `ownership.json`, make the edit.
3. Run `python3 tools/check_ownership.py <owner>` — must not list "NOT ALLOWED" files.
4. Commit with a clear message, push, open a PR to `main`. In the PR description list the changed URLs.
5. Cloudflare comments a **preview link** on the PR within ~1 minute:
   `https://<branch>-apulainen-pro.apulainen-pro.workers.dev/<path>` (branch name with `/` becomes `-`).
   Check the page on desktop and at 390 px.
6. Merge when the preview looks right. Only-own-files PRs: the owner merges. PRs with SHARED files: the other owner approves first.
   Merging to `main` publishes to `https://apulainen-pro.apulainen-pro.workers.dev`.

## 7. Example: "change the prices section on /muuttosiivous-vantaa"
1. URL `/muuttosiivous-vantaa` → file `public/muuttosiivous-vantaa.html`; `ownership.json` says owner `partner`.
2. Branch `partner/muuttosiivous-vantaa-hinnat`.
3. In the file, find `<h2 class="disp">Muuttosiivous hinta Vantaa</h2>`; its `<section class="blk">` is the block to edit.
   Change texts/prices inside that section using only §4 components (e.g. a `.tbl` table or `.grid g3` of `.card`s).
4. If the page `<title>`/description mention prices, keep them consistent.
5. `python3 tools/check_ownership.py partner` → OK. Commit, push, PR, check the preview link, merge.

## 8. Adding a new page
Create the file by copying a similar page (same `<head>` structure, header, contact block, footer), set a unique
`<title>`, description and canonical, add it to `ownership.json` → `files` with your owner, and link to it from a
related page. New URLs need no redirect.
