#!/usr/bin/env python3
"""Build the new Apulainen.pro static site from a Tilda export.

Usage:
    python3 migration/build_from_tilda.py <path-to-unzipped-export/apulainen.pro> [repo-root]

What it does
- Reads Tilda's `htaccess` to learn which pageNNN.html file serves which URL.
- Extracts the content of every page (headings, texts, lists, tables, FAQ,
  cards, images, internal links) and re-renders it in the new design.
- Keeps every URL path, <title>, meta description, canonical and JSON-LD,
  so search positions are not lost.
- Writes `public/_redirects` (Tilda's own 301s + technical/old pages).
- Copies only the images the pages use, resized to max 1600 px.

`public/index.html` (the approved homepage mockup) is NOT overwritten; only its
title/description/canonical are refreshed from Tilda's home page.
"""
import html as H
import json
import os
import re
import sys
from bs4 import BeautifulSoup, NavigableString, Tag, Comment

EXPORT = os.path.abspath(sys.argv[1])
ROOT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..'))
PUB = os.path.join(ROOT, 'public')
SITE = 'https://apulainen.pro'
WA = 'https://wa.me/358417232410'
EMAIL = 'apulainen.tilaus@gmail.com'
YTUNNUS = 'Ksm Service Oy, Y-tunnus 3528429-3'

SKIP_TYPES = {'702', '967', '966', '420', '389', '704', '215', '410', '1331', '147', '191'}
SKIP_PATHS = {'/header', '/footer', '/test', '/1', '/etusivu-2026', '/ongelma'}
HOME_FILE = None
LEGACY_TARGETS = {  # Tilda paths whose page file no longer exists in the export
    '/window_cleaning': '/ikkunanpesu', '/regular_cleaning': '/kotisiivous',
    '/clearout': '/muuttosiivous', '/cleaning_after_repair': '/remonttisiivous',
    '/office_cleaning': '/toimistosiivous', '/contacts': '/yhteystiedot', '/tilaus': '/',
}

# ---------------------------------------------------------------- URL map
ht = open(os.path.join(EXPORT, 'htaccess'), encoding='utf-8').read()
m = re.search(r'^DirectoryIndex (\S+)', ht, re.M)
HOME_FILE = m.group(1) if m else None
page_paths, redirects = {}, []
for src, dst, flags in re.findall(r'^RewriteRule \^(.*?)\$ (\S+) \[([^\]]*)\]', ht, re.M):
    if 'R=301' in flags:
        if src != '(.*)':
            redirects.append(('/' + src, dst.replace('\\', '')))
    elif dst.startswith('page'):
        lst = page_paths.setdefault(dst, [])
        if '/' + src not in lst:
            lst.append('/' + src)

known = json.load(open(os.path.join(ROOT, 'migration', 'tilda-pages.json'), encoding='utf-8'))
known_paths = {k['path'] for k in known}


def norm(p):
    return (p.rstrip('/') or '/').lower()


# --------------------------------------------------------------- helpers
def esc(t):
    return H.escape(t, quote=True)


def squash(t):
    return re.sub(r'\s+', ' ', t or '').strip()


PATH_OF_FILE = {}
IMAGES = {}  # export-relative -> public url


def fix_href(href):
    """Return a usable href or None. Popups / phone links become WhatsApp."""
    if not href:
        return None
    h = href.strip()
    if h.startswith(('#popup', '#order', 'tel:')) or 'wa.me' in h or 'whatsapp' in h:
        return WA
    if h.startswith(('#', 'javascript:')):
        return None
    if h.startswith('mailto:'):
        return h
    h = re.sub(r'^(https?:)?//(www\.)?apulainen\.pro', '', h)
    if h == '':
        return '/'
    dead = {'/ukk/kotisiivous': '/ukk', '/ukk/muuttosiivous': '/ukk', '/kotisiivous-tampere': '/kotisiivous'}
    if h.split('#')[0] in dead:  # links that were already broken on Tilda
        return dead[h.split('#')[0]]
    if h.startswith('/') and h != h.lower() and not h.startswith('/images/'):
        h = h.lower()  # Tilda matched URLs case-insensitively
    mm = re.match(r'^/?(page\d+\.html)(.*)$', h)
    if mm and mm.group(1) in PATH_OF_FILE:
        return PATH_OF_FILE[mm.group(1)] + mm.group(2)
    return h


def img_url(src):
    """Copy (resized) image into public/images and return its URL, or None."""
    if not src or not src.startswith('images/'):
        return None
    if 'lib__icons' in src or 'noroot' in src or src.lower().endswith(('.svg', '.gif')):
        return None
    if src in IMAGES:
        return IMAGES[src]
    path = os.path.join(EXPORT, src)
    if not os.path.exists(path):
        IMAGES[src] = None
        return None
    from PIL import Image
    name = os.path.basename(src)
    stem = re.sub(r'\.(jpe?g|png|webp)$', '', name, flags=re.I)
    out = os.path.join(PUB, 'images', stem + '.webp')
    url = '/images/' + stem + '.webp'
    try:
        if not os.path.exists(out):
            im = Image.open(path)
            if im.width < 120:
                IMAGES[src] = None
                return None
            if im.mode not in ('RGB', 'RGBA'):
                im = im.convert('RGBA' if 'A' in im.mode or 'transparency' in im.info else 'RGB')
            if im.width > 1600:
                im = im.resize((1600, round(im.height * 1600 / im.width)))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            im.save(out, 'WEBP', quality=78, method=4)
    except Exception as e:  # unreadable image -> skip
        print('  image skipped', src, e)
        IMAGES[src] = None
        return None
    IMAGES[src] = url
    return url


INLINE_KEEP = {'strong': 'strong', 'b': 'strong', 'em': 'em', 'i': 'em'}


def inline(node):
    """Sanitised inline HTML of a node's children."""
    out = []
    for c in node.children:
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            out.append(esc(str(c)))
            continue
        if not isinstance(c, Tag) or c.name in ('script', 'style', 'svg', 'noscript', 'img', 'button', 'input', 'form'):
            continue
        if c.name == 'br':
            out.append('<br>')
        elif c.name in INLINE_KEEP:
            inner = inline(c)
            if squash(re.sub(r'<[^>]+>', '', inner)):
                out.append(f'<{INLINE_KEEP[c.name]}>{inner}</{INLINE_KEEP[c.name]}>')
            else:
                out.append(inner)
        elif c.name == 'a':
            href = fix_href(c.get('href'))
            inner = inline(c)
            if href:
                ext = href.startswith('http') and not href.startswith(WA)
                rel = ' rel="noopener" target="_blank"' if ext else ''
                out.append(f'<a href="{esc(href)}"{rel}>{inner}</a>')
            else:
                out.append(inner)
        elif c.name in ('ul', 'ol'):
            lis = ''.join(f'<li>{inline(li).strip()}</li>' for li in c.find_all('li', recursive=False))
            out.append(f'<{c.name}>{lis}</{c.name}>')
        elif c.name in ('p', 'div', 'li'):
            inner = inline(c).strip()
            if inner:
                out.append(inner + '<br>')
        else:
            out.append(inline(c))
    s = ''.join(out)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'(\s*<br>\s*){3,}', '<br><br>', s)
    s = re.sub(r'^(\s*<br>\s*)+|(\s*<br>\s*)+$', '', s)
    return s.strip()


def text_of(html_s):
    return squash(H.unescape(re.sub(r'<[^>]+>', ' ', html_s)))


# ----------------------------------------------------------- extraction
BLOCKISH = {'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'table', 'section', 'article',
            'li', 'img', 'details', 'header', 'footer', 'figure', 'blockquote'}
CARD_RE = re.compile(r'(__col\b|__col_|t-item|card(?!-)|__item\b|t-slds__item\b|js-product\b|__card\b)')


def field_role(el):
    f = re.sub(r'__\d+$', '', el.get('field', ''))
    hd = el if re.match(r'h[1-6]$', el.name or '') else el.find(re.compile(r'^h[1-6]$'))
    if hd is not None:
        return 'h' + hd.name[1]
    if 'button' in f:
        return 'btn'
    if f in ('btitle', 'title', 'ttitle'):
        return 'h2'
    if f in ('li_title', 'li_persname', 'li_name', 'imgtitle', 'li_heading'):
        return 'h3'
    if 'subtitle' in f or 'uptitle' in f or f == 'sbtitle':
        return 'kicker'
    if 'price' in f:
        return 'price'
    return 'text'


def is_leaf(el):
    for d in el.descendants:
        if isinstance(d, Tag) and (d.name in BLOCKISH or d.has_attr('field')):
            return False
    return True


def img_of(el):
    src = el.get('data-original') or el.get('data-lazy-src') or (el.get('src') if el.name == 'img' else None)
    return img_url(src)


def walk(node, items, in_card=False):
    for c in node.children:
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            t = squash(str(c))
            if len(t) > 1:
                items.append(('text', esc(t)))
            continue
        if not isinstance(c, Tag):
            continue
        name = c.name
        cls = ' '.join(c.get('class', []))
        if name in ('script', 'style', 'noscript', 'form', 'input', 'select', 'textarea', 'svg', 'iframe',
                    'link', 'meta', 'video', 'label'):
            continue
        if re.search(r't-form|t-popup|t-slds__arrow|t-slds__bullet|js-form|t-input|tn-elem__btn-|t-slds__item_dummy', cls):
            continue
        if c.has_attr('field'):
            role = field_role(c)
            if role == 'btn':
                a = c if c.name == 'a' else c.find_parent('a')
                href = fix_href(a.get('href')) if a else None
                label = squash(c.get_text(' '))
                if href and label:
                    items.append(('btn', href, label))
                continue
            content = inline(c) if not role.startswith('h') else inline(c.find(re.compile(r'^h[1-6]$')) or c)
            if text_of(content):
                items.append((role, content))
            continue
        if c.get('itemtype', '').endswith('/Question'):
            q = c.find(attrs={'itemprop': 'name'})
            a = c.find(attrs={'itemprop': 'acceptedAnswer'})
            if q and a:
                items.append(('faq', inline(q), inline(a)))
                continue
        if name == 'details':
            s = c.find('summary')
            if s:
                q = inline(s)
                s.extract()
                items.append(('faq', q, inline(c)))
                continue
        if re.match(r'h[1-6]$', name):
            t = inline(c)
            if text_of(t):
                items.append(('h' + name[1], t))
            continue
        if name in ('ul', 'ol'):
            lis = c.find_all('li', recursive=False)
            if lis and all(is_leaf(li) for li in lis):
                body = ''.join(f'<li>{inline(li)}</li>' for li in lis if text_of(inline(li)))
                if body:
                    items.append(('list', f'<{name}>{body}</{name}>'))
                continue
        if name == 'table':
            rows = []
            for tr in c.find_all('tr'):
                cells = ''.join(f'<{td.name}>{inline(td)}</{td.name}>' for td in tr.find_all(['td', 'th']))
                rows.append(f'<tr>{cells}</tr>')
            if rows:
                items.append(('table', '<table>' + ''.join(rows) + '</table>'))
            continue
        if name == 'img' or c.has_attr('data-original'):
            u = img_of(c)
            if u:
                items.append(('img', u, squash(c.get('alt') or c.get('title') or '')))
            if name == 'img':
                continue
        if name == 'a' and is_leaf(c):
            href = fix_href(c.get('href'))
            label = squash(c.get_text(' '))
            if href and label and label.lower() not in ('button', 'read more'):
                items.append(('link', href, label))
            elif label:
                items.append(('text', esc(label)))
            continue
        if is_leaf(c):
            t = inline(c) if name != 'li' else inline(c)
            if text_of(t):
                items.append(('text', t))
            continue
        sib = [x for x in node.find_all(True, recursive=False) if x.get('class') == c.get('class')]
        if not in_card and c.get('class') and len(sib) >= 2 and not is_leaf(c):
            sub = []
            walk(c, sub, True)
            if sub:
                items.append(('card', sub))
            continue
        walk(c, items, in_card)


def zero_block(rec, items):
    els = []
    for e in rec.select('.tn-elem'):
        try:
            top = float(e.get('data-field-top-value') or 0)
            left = float(e.get('data-field-left-value') or 0)
        except ValueError:
            top = left = 0
        els.append((top, left, e))
    els.sort(key=lambda x: (x[0], x[1]))
    for _, _, e in els:
        t = e.get('data-elem-type')
        if t == 'text':
            atom = e.select_one('.tn-atom') or e
            hd = atom.find(re.compile(r'^h[1-6]$'))
            content = inline(hd or atom)
            if not text_of(content):
                continue
            try:
                fs = float(e.get('data-field-fontsize-value') or 16)
            except ValueError:
                fs = 16
            role = ('h' + hd.name[1]) if hd else ('h2' if fs >= 26 and len(text_of(content)) < 140 else 'text')
            items.append((role, content))
        elif t in ('image', 'shape'):
            for d in [e] + e.select('[data-original], img'):
                u = img_of(d)
                if u:
                    items.append(('img', u, squash(d.get('alt') or '')))
                    break
        elif t == 'button':
            a = e.find('a')
            href = fix_href(a.get('href')) if a else None
            label = squash(e.get_text(' '))
            if href and label:
                items.append(('btn', href, label))


EN_STOP = set('the and you your our with for that this from are can will about of to is'.split())


PAGE_FI = [True]


def junk(text):
    """Leftover template blocks (English/Russian demo content) on Finnish pages."""
    if re.search(r'[а-яА-ЯёЁ]{4,}', text):
        return True
    if not PAGE_FI[0]:
        return False
    words = re.findall(r'[a-zäöå]+', text.lower())
    if len(words) < 8:
        return False
    en = sum(w in EN_STOP for w in words) / len(words)
    fi = sum(('ä' in w or 'ö' in w) for w in words) / len(words)
    return en > 0.05 and fi < 0.02


def pair_faq(items):
    out, i = [], 0
    while i < len(items):
        it = items[i]
        if it[0] in ('h3', 'h4', 'h2') and i + 1 < len(items) and items[i + 1][0] == 'text':
            ans = [items[i + 1][1]]
            j = i + 2
            while j < len(items) and items[j][0] == 'text':
                ans.append(items[j][1])
                j += 1
            out.append(('faq', it[1], '<br><br>'.join(ans)))
            i = j
        else:
            out.append(it)
            i += 1
    return out


def extract_rec(rec, seen):
    t = rec.get('data-record-type')
    if t in SKIP_TYPES:
        return []
    cls = ' '.join(rec.get('class', []))
    if 't-screenmax-' in cls:  # mobile-only duplicate
        return []
    items = []
    for tp in rec.find_all('template'):
        tp.decompose()
    p1 = rec.select_one('.t431__data-part1')
    if p1 is not None:
        p2 = rec.select_one('.t431__data-part2')
        rows = [p1.get_text()] + ((p2.get_text().split('\n')) if p2 else [])
        trs = ''.join('<tr>' + ''.join(f'<td>{esc(squash(c))}</td>' for c in r.split(';')) + '</tr>'
                      for r in rows if squash(r))
        for x in rec.select('.t431__data-part1, .t431__data-part2'):
            x.decompose()
        walk(rec, items)
        items.append(('table', '<table>' + trs + '</table>'))
    elif rec.select_one('.t396__artboard'):
        zero_block(rec, items)
    else:
        walk(rec, items)
    if junk(squash(rec.get_text(' '))):
        return ['JUNK']
    html_s = str(rec)
    if t in ('585', '668', '1152') or re.search(r'accordion', html_s[:20000]):
        items = pair_faq(items)

    # de-duplicate (Tilda repeats texts for mobile/desktop)
    def dedup(lst):
        res = []
        for it in lst:
            if it[0] == 'card':
                sub = dedup(it[1])
                if sub:
                    res.append(('card', sub))
                continue
            key = (it[0], text_of(it[1]) if it[0] not in ('img', 'link', 'btn') else it[1] + (it[2] if len(it) > 2 else ''))
            k2 = key[1] if isinstance(key[1], str) else ''
            if it[0] == 'img' or len(k2) > 24:
                if key in seen:
                    continue
                seen.add(key)
            if res and res[-1] == it:
                continue
            res.append(it)
        return res
    return dedup(items)


# --------------------------------------------------------------- render
def render_items(items, page, depth=0):
    out = []
    i = 0
    while i < len(items):
        it = items[i]
        k = it[0]
        if k == 'card':
            group = []
            while i < len(items) and items[i][0] == 'card':
                group.append(items[i][1])
                i += 1
            out.append(render_cards(group, page))
            continue
        if k == 'faq':
            group = []
            while i < len(items) and items[i][0] == 'faq':
                group.append(items[i])
                i += 1
            page['faq'].extend(group)
            out.append('<div class="faq">' + ''.join(
                f'<details><summary>{q}</summary><div class="ans">{a}</div></details>' for _, q, a in group) + '</div>')
            continue
        if k == 'img':
            group = []
            while i < len(items) and items[i][0] == 'img':
                group.append(items[i])
                i += 1
            if not page['ogimg']:
                page['ogimg'] = group[0][1]
            cls = 'gal' if len(group) > 1 else 'gal one'
            alt_def = esc(page['h1text'] or page['title'])
            out.append(f'<div class="{cls}">' + ''.join(
                f'<img src="{u}" alt="{esc(a) or alt_def}" loading="lazy" decoding="async">' for _, u, a in group[:12]) + '</div>')
            continue
        if k in ('btn', 'link'):
            group = []
            while i < len(items) and items[i][0] in ('btn', 'link'):
                group.append(items[i])
                i += 1
            internal = [g for g in group if g[1].startswith('/')]
            if len(group) >= 4 and len(internal) >= len(group) * .6:
                out.append('<ul class="links">' + ''.join(f'<li><a href="{esc(h)}">{esc(l)}</a></li>' for _, h, l in group) + '</ul>')
            else:
                bt = []
                for _, h, l in group:
                    if h == WA:
                        bt.append(f'<a class="btn" href="{WA}">{WA_ICON}{esc(l)}</a>')
                    elif k == 'btn' or len(l) < 40:
                        bt.append(f'<a class="btn ghost" href="{esc(h)}">{esc(l)}</a>')
                    else:
                        bt.append(f'<p><a href="{esc(h)}">{esc(l)}</a></p>')
                out.append('<div class="acts">' + ''.join(dict.fromkeys(bt)) + '</div>')
            continue
        i += 1
        if k[0] == 'h' and k[1:].isdigit():
            lvl = int(k[1])
            if lvl == 1:
                if page['h1done']:
                    lvl = 2
                else:
                    page['h1done'] = True
                    page['h1text'] = text_of(it[1])
            if depth:
                lvl = max(lvl, 3)
            lvl = min(lvl, 4)
            cl = ' class="disp"' if lvl <= 2 else ''
            out.append(f'<h{lvl}{cl}>{it[1]}</h{lvl}>')
        elif k == 'kicker':
            out.append(f'<div class="kicker">{it[1]}</div>')
        elif k == 'price':
            out.append(f'<div class="price">{it[1]}</div>')
        elif k in ('list', 'table'):
            out.append(it[1] if k == 'list' else f'<div class="tbl">{it[1]}</div>')
        else:
            out.append(f'<p>{it[1]}</p>')
    return '\n'.join(out)


def render_cards(group, page):
    # cards that are only a link -> chip list (district/city lists)
    flat = [c for c in group]
    if all(len(c) == 1 and c[0][0] in ('link', 'btn') for c in flat) or \
       all(len(c) <= 2 and any(x[0] == 'link' for x in c) and not any(x[0] in ('text', 'img') for x in c) for c in flat):
        links = [x for c in flat for x in c if x[0] in ('link', 'btn')]
        return '<ul class="links">' + ''.join(f'<li><a href="{esc(h)}">{esc(l)}</a></li>' for _, h, l in links) + '</ul>'
    # heading cards whose title is a link -> convert to linked card
    cards = []
    for c in group:
        if not c:
            continue
        if len(c) > 1 and c[0][0] == 'text' and len(text_of(c[0][1])) < 70 and not any(x[0][0] == 'h' and x[0][1:].isdigit() for x in c):
            c = [('h3', c[0][1])] + c[1:]
        cards.append('<div class="card">' + render_items(c, page, 1) + '</div>')
    n = len(cards)
    col = 'g3' if n % 3 == 0 or n > 4 else ('g2' if n in (2, 4) else 'g1')
    return f'<div class="grid {col}">' + ''.join(cards) + '</div>'


WA_ICON = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-12.4 '
           '7.4L3 21l2.1-5.4A8.4 8.4 0 1 1 21 11.5z"></path></svg>')

NAV = [('/ikkunanpesu', 'Ikkunanpesu'), ('/kotisiivous', 'Kotisiivous'), ('/muuttosiivous', 'Muuttosiivous'),
       ('/hinnasto', 'Hinnasto'), ('/referenssit', 'Referenssit'), ('/yhteystiedot', 'Yhteystiedot')]
FOOT_SERV = [('/ikkunanpesu', 'Ikkunanpesu'), ('/kotisiivous', 'Kotisiivous'), ('/muuttosiivous', 'Muuttosiivous'),
             ('/loppusiivous', 'Loppusiivous'), ('/remonttisiivous', 'Remonttisiivous'), ('/suursiivous', 'Suursiivous'),
             ('/kylpyhuonesiivous', 'Kylpyhuonesiivous'), ('/toimistosiivous', 'Toimistosiivous'),
             ('/ilmalmppumpun_puhdistus', 'Ilmalämpöpumpun puhdistus'), ('/joulusiivous', 'Joulusiivous')]
FOOT_CITY = [('/ikkunanpesu/helsinki', 'Ikkunanpesu Helsinki'), ('/ikkunanpesu/porvoo', 'Ikkunanpesu Porvoo'),
             ('/ikkunanpesu/kotka', 'Ikkunanpesu Kotka'), ('/ikkunanpesu/kouvola', 'Ikkunanpesu Kouvola'),
             ('/ikkunanpesu/turku', 'Ikkunanpesu Turku'), ('/kotisiivous/helsinki', 'Kotisiivous Helsinki'),
             ('/kotisiivous/espoo', 'Kotisiivous Espoo'), ('/kotisiivous/porvoo', 'Kotisiivous Porvoo'),
             ('/kotisiivous/kotka', 'Kotisiivous Kotka'), ('/kotisiivous/kouvola', 'Kotisiivous Kouvola')]
FOOT_INFO = [('/hinnasto', 'Hinnasto'), ('/referenssit', 'Referenssit'), ('/arvostelut', 'Arvostelut'),
             ('/blogi', 'Blogi'), ('/ukk', 'UKK'), ('/videot', 'Videot'), ('/lahjakortti', 'Lahjakortti'),
             ('/tietoa-meista/', 'Tietoa meistä'), ('/typaikat-puhdistusalalla', 'Työpaikat'),
             ('/tietosuojaseloste', 'Tietosuojaseloste')]


def header():
    nav = ''.join(f'<a href="{h}">{t}</a>' for h, t in NAV)
    return f'''<header class="top"><div class="wrap">
<a class="logo" href="/">APULAINEN<span>.PRO</span></a>
<nav class="nav" aria-label="Päävalikko">{nav}</nav>
<a class="btn sm" href="{WA}">{WA_ICON}<span class="hide-m">WhatsApp</span></a>
<details class="mnav"><summary aria-label="Valikko"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg></summary><div>{nav}</div></details>
</div></header>'''


def footer():
    col = lambda title, lst: f'<div class="fcol"><b>{title}</b>' + ''.join(f'<a href="{h}">{t}</a>' for h, t in lst) + '</div>'
    return f'''<footer class="foot"><div class="wrap fgrid">
<div class="fcol"><span class="logo">APULAINEN<span>.PRO</span></span><span class="muted">Siivous ja ikkunanpesu kotiin ja yrityksille. {YTUNNUS}</span>
<a href="{WA}">WhatsApp</a><a href="mailto:{EMAIL}">{EMAIL}</a><span class="muted">Asiakaspalvelu ma–pe 9–18</span></div>
{col('Palvelut', FOOT_SERV)}{col('Kaupungit', FOOT_CITY)}{col('Tietoa', FOOT_INFO)}
</div><div class="wrap copy">© 2020–2026 Apulainen.pro</div></footer>'''


def contact_block():
    return f'''<section class="sec" id="yhteys"><div class="wrap"><div class="cta">
<div><h2 class="disp">Pyydä hinta-arvio</h2>
<p>Kerro viestissä palvelu, paikkakunta ja kohteen koko. Kuvat kohteesta nopeuttavat arviota. Vastaamme arkisin ma–pe 9–18.</p></div>
<div class="acts"><a class="btn yel" href="{WA}">{WA_ICON}Kirjoita WhatsAppiin</a>
<a class="btn ghost light" href="mailto:{EMAIL}">{EMAIL}</a></div>
</div></div></section>'''


def crumbs(path, titles):
    parts = [p for p in path.strip('/').split('/') if p]
    if len(parts) < 2:
        return ''
    out = ['<a href="/">Etusivu</a>']
    acc = ''
    for p in parts[:-1]:
        acc += '/' + p
        name = p.replace('-', ' ').replace('_', ' ').capitalize() if norm(acc) in titles else None
        if name:
            out.append(f'<a href="{acc}">{esc(name)}</a>')
    return '<nav class="crumbs" aria-label="Murupolku">' + ' <span>›</span> '.join(out) + '</nav>'


def head(page):
    ld = ''.join(f'<script type="application/ld+json">{x}</script>\n' for x in page['ld'])
    og = f'<meta property="og:image" content="{SITE}{page["ogimg"]}">' if page['ogimg'] else ''
    return f'''<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>{esc(page['title'])}</title>
<meta name="description" content="{esc(page['desc'])}">
<link rel="canonical" href="{esc(page['canonical'])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(page['canonical'])}">
<meta property="og:title" content="{esc(page['ogtitle'] or page['title'])}">
<meta property="og:description" content="{esc(page['ogdesc'] or page['desc'])}">
{og}
<link rel="icon" href="/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/assets/site.css">
{ld}</head>'''


# ------------------------------------------------------------- main loop
def file_for(path):
    p = path.split('?')[0]
    if p == '/':
        return 'index.html'
    if p.endswith('/'):
        return p.strip('/') + '/index.html'
    return p.strip('/') + '.html'


def pick_path(fname, soup):
    paths = page_paths[fname]
    can = soup.find('link', rel='canonical')
    can = re.sub(r'^https?://(www\.)?apulainen\.pro', '', can['href']) if can and can.get('href') else None
    if can is not None and (can == '' or can in paths):
        return can or '/', paths
    for p in paths:
        if p in known_paths:
            return p, paths
    return paths[0].rstrip('/') or '/', paths


def main():
    soups, chosen = {}, {}
    for fname in page_paths:
        fp = os.path.join(EXPORT, fname)
        if not os.path.exists(fp):
            continue
        soups[fname] = BeautifulSoup(open(fp, encoding='utf-8').read(), 'lxml')
        path, _ = pick_path(fname, soups[fname])
        chosen[fname] = path
        PATH_OF_FILE[fname] = path
    titles = {}
    for fname, s in soups.items():
        h1 = s.find('h1')
        t = squash(h1.get_text(' ')) if h1 else squash(s.title.string if s.title else '')
        titles[norm(chosen[fname])] = t[:60]

    css_src = os.path.join(ROOT, 'migration', 'site.css')
    os.makedirs(os.path.join(PUB, 'assets'), exist_ok=True)
    with open(css_src, encoding='utf-8') as f, open(os.path.join(PUB, 'assets', 'site.css'), 'w', encoding='utf-8') as o:
        o.write(f.read())

    report = {'pages': [], 'junk_blocks': [], 'skipped': []}
    generated = set()
    for fname, s in soups.items():
        path = chosen[fname]
        if fname == HOME_FILE:
            refresh_home(s)
            generated.add('/')
            continue
        if norm(path) in SKIP_PATHS:
            report['skipped'].append(path)
            continue
        ld = [x.string.strip() for x in s.find_all('script', type='application/ld+json') if x.string and x.string.strip()]
        md = s.find('meta', attrs={'name': 'description'})
        ogt = s.find('meta', property='og:title')
        ogd = s.find('meta', property='og:description')
        ogi = s.find('meta', property='og:image')
        page = {'title': squash(s.title.string if s.title else ''), 'desc': md.get('content', '') if md else '',
                'canonical': SITE + (path if path != '/' else '/'), 'ogtitle': ogt.get('content') if ogt else '',
                'ogdesc': ogd.get('content') if ogd else '', 'ogimg': img_url(ogi.get('content')) if ogi else None,
                'ld': ld, 'faq': [], 'h1done': False, 'h1text': ''}
        seen = set()
        sections = []
        PAGE_FI[0] = len(re.findall(r'[äöÄÖ]', (s.find(id='allrecords') or s.body).get_text())) > 150
        body = s.find(id='allrecords') or s.body
        for rec in body.select('div.r.t-rec'):
            items = extract_rec(rec, seen)
            if items == ['JUNK']:
                report['junk_blocks'].append((path, rec.get('id')))
                continue
            if not items:
                continue
            has_h1 = any(it[0] == 'h1' for it in items) and not page['h1done']
            inner = render_items(items, page)
            if not inner.strip():
                continue
            sections.append((has_h1, inner))
        if not page['h1done']:
            # promote: page needs one h1 -> use page title
            h1 = esc(re.split(r'\s[|–-]\s', page['title'])[0])
            sections.insert(0, (True, f'<h1 class="disp">{h1}</h1>'))
        out = [head(page), '<body>', header(), '<main>']
        hero_done = False
        for has_h1, inner in sections:
            if has_h1 and not hero_done:
                hero_done = True
                inner = inner.replace('<h2 class="disp">', '<h2 class="disp">', 1)
                out.append(f'<section class="hero"><div class="wrap">{crumbs(path, titles)}<div class="hero-in">{inner}'
                           f'<div class="acts"><a class="btn" href="{WA}">{WA_ICON}Kirjoita WhatsAppiin</a>'
                           f'<a class="btn ghost" href="#yhteys">Pyydä hinta-arvio</a></div></div></div></section>')
            else:
                out.append(f'<section class="blk"><div class="wrap">{inner}</div></section>')
        out.append(contact_block())
        out.append('</main>')
        out.append(footer())
        if page['faq'] and not any('FAQPage' in x for x in page['ld']):
            faq = {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
                {'@type': 'Question', 'name': text_of(q), 'acceptedAnswer': {'@type': 'Answer', 'text': text_of(a)}}
                for _, q, a in page['faq']]}
            out.append('<script type="application/ld+json">' + json.dumps(faq, ensure_ascii=False) + '</script>')
        out.append('</body>\n</html>\n')
        html_s = '\n'.join(out)
        # sanity: one h1
        fp = os.path.join(PUB, file_for(path))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(html_s)
        generated.add(norm(path))
        report['pages'].append({'path': path, 'file': file_for(path), 'source': fname,
                                'h1': page['h1text'], 'faq': len(page['faq'])})

    # 404
    nf = soups.get('page36365964.html')
    write_404()

    # redirects
    lines = ['# Generated by migration/build_from_tilda.py – Tilda 301s and retired Tilda URLs']
    seen_src = set()

    def add(src, dst):
        dst = re.sub(r'^https?://(www\.)?apulainen\.pro', '', dst) or '/'
        base = src.rstrip('/') or '/'
        variants = [base] if base == '/' or base.endswith('.html') else [base, base + '/']
        for v in variants:
            if norm(v) in generated or v in seen_src or norm(v) == norm(dst):
                continue
            seen_src.add(v)
            lines.append(f'{v} {dst} 301')
    for src, dst in redirects:
        add(src, dst)
    for fname, path in chosen.items():
        target = '/' if (fname == HOME_FILE or norm(path) in SKIP_PATHS) else path
        add('/' + fname, target)
        for p in page_paths[fname]:
            if norm(p) in SKIP_PATHS:
                add(p, '/')
    for fname, paths in page_paths.items():
        if fname not in soups:
            for p in paths:
                add(p, LEGACY_TARGETS.get(norm(p), '/'))
    for k in known:
        if k['type'] == 'tilda-technical':
            f = k['path'].strip('/')
            add(k['path'], PATH_OF_FILE.get(f, '/'))
    with open(os.path.join(PUB, '_redirects'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    report['redirects'] = len(lines) - 1
    report['images'] = sum(1 for v in IMAGES.values() if v)
    with open(os.path.join(ROOT, 'migration', 'build-report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('pages', len(report['pages']), 'redirects', report['redirects'], 'images', report['images'],
          'junk blocks', len(report['junk_blocks']))


def refresh_home(s):
    fp = os.path.join(PUB, 'index.html')
    h = open(fp, encoding='utf-8').read()
    md = s.find('meta', attrs={'name': 'description'})
    title = squash(s.title.string if s.title else 'Apulainen.pro')
    desc = md.get('content', '') if md else ''
    h = re.sub(r'<title>.*?</title>', f'<title>{esc(title)}</title>', h, count=1, flags=re.S)
    h = re.sub(r'\n<meta name="description"[^>]*>|\n<link rel="canonical"[^>]*>', '', h)
    h = h.replace('</title>', f'</title>\n<meta name="description" content="{esc(desc)}">\n'
                              f'<link rel="canonical" href="{SITE}/">', 1)
    open(fp, 'w', encoding='utf-8').write(h)


def write_404():
    page = {'title': 'Sivua ei löytynyt | Apulainen.pro', 'desc': '', 'canonical': SITE + '/404', 'ogtitle': '',
            'ogdesc': '', 'ogimg': None, 'ld': []}
    links = ''.join(f'<li><a href="{h}">{t}</a></li>' for h, t in FOOT_SERV + [('/hinnasto', 'Hinnasto'), ('/yhteystiedot', 'Yhteystiedot')])
    html_s = '\n'.join([head(page), '<body>', header(), '<main>',
                        f'<section class="hero"><div class="wrap"><div class="hero-in"><h1 class="disp">Sivua ei löytynyt</h1>'
                        f'<p>Etsimääsi sivua ei ole tai se on siirretty. Valitse palvelu alta tai kirjoita meille.</p>'
                        f'<ul class="links">{links}</ul></div></div></section>', contact_block(), '</main>', footer(),
                        '</body>\n</html>\n'])
    open(os.path.join(PUB, '404.html'), 'w', encoding='utf-8').write(html_s)


if __name__ == '__main__':
    main()
