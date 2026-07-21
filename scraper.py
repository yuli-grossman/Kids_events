#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
סורק אירועים לילדים (גיל 3-5) מאתרי עיריות ומוסדות תרבות.
ערים: גני תקווה, קריית אונו, פתח תקווה, סביון, אור יהודה, יהוד
+ אירועים מיוחדים ברחבי המרכז (הבמה)

הרצה מקומית: python3 scraper.py
"""

import requests
from bs4 import BeautifulSoup
import re
import sys
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
import time
import html as html_mod
import json as jsonlib

# ─── Headers ─────────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'he,en-US;q=0.7,en;q=0.3',
}

# ─── Constants ───────────────────────────────────────────────────────────────

HEBREW_MONTHS = {
    'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'מרס': 3, 'אפריל': 4,
    'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
}

CITY_COLORS = {
    'גני תקווה':  '#2E7D32',
    'קריית אונו': '#1565C0',
    'פתח תקווה': '#6A1B9A',
    'סביון':      '#E65100',
    'אור יהודה':  '#AD1457',
    'יהוד':       '#00695C',
}

CHILDREN_KEYWORDS = [
    'ילדים', 'ילד', 'ילדה', 'לילדים', 'לילד',
    'גיל הרך', 'גיל הגן',
    'משפחות', 'משפחה', 'לכל המשפחה',
    'הורים וילדים', 'עם הילדים', 'עם הילד',
    'הצגה', 'הצגות', 'בובות', 'בובתיאטרון',
    'קטנטנים', 'גן ילדים', 'גני ילדים',
    'קייטנ',
    'מחזמר לילדים',
    'הרפתקה', 'הרפתקאות',
    'גיל 3', 'גיל 4', 'גיל 5', 'גיל 6',
    'גיל שלוש', 'גיל ארבע', 'גיל חמש', 'גיל שש',
    'לגיל', 'לגילאי', 'לגילאים',
    'יובל המבולבל', 'שרוליק', 'שלגיה',
    'קטנים', 'קטן', 'קטנה',
]

AGE_PATTERNS = [
    r'(?:גיל|לגילאי?|לגיל|לגילאים)\s*[3-7]',
    r'[3-7]\s*[-–]\s*[4-9]\s*(?:שנ|שנות|שנה)',
    r'(?:3|4|5|6)\s*[-–]\s*(?:5|6|7|8|9|10)',
    r'(?:ב)?גילאי?\s+(?:3|4|5|6)',
    r'גיל הרך',
    r'לכל המשפח',
    r'\bילדים\b',
    r'גיל הגן',
    r'קייטנ',
    r'א[׳\']\s*[-–]',  # grade aleph+
]

EXCLUDE_KEYWORDS = [
    'לנוער בלבד', 'למבוגרים בלבד', 'לבוגרים בלבד',
    'אזרחים ותיקים', 'לסטודנטים', 'לעסקים',
    'ותיקים', 'קשישים', 'נוער בלבד',
    'אולם פתוח בוגרים',
]

ADULT_ONLY_PATTERNS = [
    r'(?:^|\s)(?:לבוגרים|למבוגרים|לנשים|לגברים|לזוגות)(?:\s|$|,)',
    r'ריתוך',
    r'(?:^|\s)סדנת\s+(?:כתיבה|צילום|יין|בישול\s+מתקדם)(?:\s|$)',
    r'(?:^|\s)(?:ערב\s+זול|בר\s+מצוה|בת\s+מצוה)(?:\s|$)',
    r'לנוער\s+(?:בלבד|18|16)',
    r'אולם פתוח בוגרים',
    r'(?:^|\s)סטנד.?אפ(?:\s|$)',  # stand-up comedy
]

# Events clearly only for infants (age 0-2), not relevant for 3-5 year olds.
# We exclude these UNLESS the event also mentions ages 3+ explicitly.
INFANT_ONLY_PATTERNS = [
    r'לגילאי?\s+0\s*[-–]\s*[12](?:\s|שנ|$|\b)',
    r'(?:גיל|לגיל)\s+0\s*[-–]\s*2',
    r'(?:מ)?לידה\s+(?:עד|ל)\s+(?:גיל\s+)?(?:שנה\b|שנה\s+וחצי|שנתיים)',
    r'0\s*[-–]\s*(?:24|18|12)\s*חודשים',
    r'גיל\s+חודשים',
    r'(?:מ\s*)?לידה\s*[-–]\s*(?:שנה|שנתיים|18|24)',
    r'(?:מ\s*)?(?:לידה|0)\s*[-–]\s*(?:שנה|שנתיים)',
    r'(?:אמא|אבא)\s+ותינוק\b',  # "אמא ותינוק" without broader age
    r'בוקר\s+(?:עם\s+)?(?:אמא|אבא)\s+ותינוק',
    r'תינוקות\s+(?:0|מ)?[-–]?\s*(?:שנה|שנתיים|24|18|12)\s*(?:חודשים?)?$',
]

# Presence of any of these indicates the event includes ages 3+ (so don't exclude)
INCLUDES_OLDER_PATTERN = re.compile(
    r'גיל\s+[3-9]|[3-9]\s*[-–]\s*\d+\s*שנ|לכל המשפח|גיל הגן|גן\s+ילדים|'
    r'(?:3|4|5|6|7)\s*[-–]\s*(?:5|6|7|8|9|10)|גיל\s+(?:שלוש|ארבע|חמש|שש)'
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def extract_age_label(title, description='', category='', audience=''):
    """Return a short Hebrew age label, e.g. 'גיל 3-6' or 'לכל המשפחה'."""
    combined = f'{title} {description} {category} {audience}'

    # Explicit range: לגילאי/גיל X-Y  or  X-Y שנ
    m = re.search(r'(?:לגילאי?|גיל|לגיל|לגילאים)\s*(\d+)\s*[-–]\s*(\d+)', combined)
    if m:
        return f'גיל {m.group(1)}-{m.group(2)}'

    m = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*שנ', combined)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a <= 12 and a < b:
            return f'גיל {a}-{b}'

    # "מגיל X" or "מגיל X ומעלה"
    m = re.search(r'מגיל\s*(\d+)', combined)
    if m:
        return f'מגיל {m.group(1)}+'

    # Single age: גיל/לגיל X
    m = re.search(r'(?:לגילאי?|גיל|לגיל)\s*(\d+)', combined)
    if m:
        age = int(m.group(1))
        if 1 <= age <= 12:
            return f'גיל {age}+'

    # Named ranges
    if re.search(r'לכל המשפח', combined):
        return 'לכל המשפחה'
    if 'גיל הרך' in combined:
        return 'גיל הרך'
    if 'גיל הגן' in combined:
        return 'גיל הגן'
    if re.search(r'פעוטות?|פעוטון', combined):
        return 'פעוטות'
    if 'תינוקות' in combined or 'תינוק' in combined:
        return 'תינוקות'

    return ''


def classify_event_type(title, description='', category=''):
    """Return a Hebrew event-type label for grouping and display."""
    combined = f'{title} {description} {category}'
    if re.search(r'הצג[הות]|מחזמר|בובות|תיאטר|פאפטשואו|פופטשואו', combined):
        return 'הצגות'
    if re.search(r'קייטנ', combined):
        return 'קייטנות'
    if re.search(r'פסטיבל|פסטה|קרנבל|חגיגה', combined):
        return 'פסטיבלים'
    if re.search(r'תערוכ[הת]|גלרי[הת]|מוזיאון', combined):
        return 'תערוכות'
    if re.search(r'סדנ[אה]ה?', combined):
        return 'סדנאות'
    if re.search(r'קונצרט|הופע[הת]|להקה|מוסיקה', combined):
        return 'מוסיקה'
    if re.search(r'ספרייה|ספר |קריאה|שעת\s+סיפור', combined):
        return 'ספרייה'
    if re.search(r'ספורט|שחיי|כדורגל|כדורסל|יוגה|התעמלות', combined):
        return 'ספורט'
    return 'אחר'


def fetch(url, timeout=18):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = 'utf-8'
        return BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        print(f'  ⚠  שגיאה {url}: {e}', file=sys.stderr)
        return None


def fetch_json(url, timeout=12):
    try:
        r = requests.get(url, headers={**HEADERS, 'Accept': 'application/json'}, timeout=timeout)
        r.encoding = 'utf-8'
        return r.json()
    except Exception as e:
        print(f'  ⚠  JSON שגיאה {url}: {e}', file=sys.stderr)
        return None


def parse_date(text):
    if not text:
        return None
    text = str(text).strip()
    today = date.today()

    m = re.search(r'(202\d)[-/](\d{2})[-/](\d{2})', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    for heb_month, month_num in HEBREW_MONTHS.items():
        if heb_month in text:
            year_m = re.search(r'(202\d)', text)
            year = int(year_m.group(1)) if year_m else today.year
            day_m = re.search(r'\b(\d{1,2})\b', text)
            if day_m:
                day = int(day_m.group(1))
                try:
                    d = date(year, month_num, day)
                    if not year_m and (today - d).days > 45:
                        d = date(year + 1, month_num, day)
                    return d
                except ValueError:
                    pass
    return None


def format_date_display(d):
    if not d:
        return None
    DAY_NAMES = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']
    MONTH_NAMES = ['', 'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
                   'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']
    return f'יום {DAY_NAMES[d.weekday()]}, {d.day} ב{MONTH_NAMES[d.month]} {d.year}'


def is_children_event(title, description='', category='', audience=''):
    combined = f'{title} {description} {category} {audience}'

    for excl in EXCLUDE_KEYWORDS:
        if excl in combined:
            return False, 0
    for pattern in ADULT_ONLY_PATTERNS:
        if re.search(pattern, combined):
            return False, 0

    # Exclude infant-only events unless they also include ages 3+
    for pattern in INFANT_ONLY_PATTERNS:
        if re.search(pattern, combined):
            if not INCLUDES_OLDER_PATTERN.search(combined):
                return False, 0

    score = 0
    for kw in CHILDREN_KEYWORDS:
        if kw in combined:
            score += 2
    for pattern in AGE_PATTERNS:
        if re.search(pattern, combined):
            score += 3
    return score > 0, score


def clean_description(text):
    if not text:
        return ''
    text = html_mod.unescape(str(text))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if text.lower() in ('description', 'none'):
        return ''
    return text[:300]


def esc(text):
    """HTML-escape a string for safe inline use."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def make_event(city, title, date_val, date_text, url,
               description='', category='', audience='', score=0,
               special=False, image=''):
    d = date_val if isinstance(date_val, date) else parse_date(date_val or date_text)
    return {
        'city': city,
        'title': title.strip(),
        'date': d,
        'date_text': date_text or '',
        'url': url,
        'description': clean_description(description),
        'category': category,
        'audience': audience,
        'score': score,
        'special': special,
        'image': image,
        'age_label': extract_age_label(title, description, category, audience),
        'event_type': classify_event_type(title, description, category),
    }


# ─── Description enrichment ──────────────────────────────────────────────────

def fetch_event_description(url, title='', timeout=9):
    """Fetch a short description from an event detail page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')
    except Exception:
        return ''

    title_stripped = title.strip().lower()

    # 1. Open Graph / meta description — most reliable across sites
    for attrs in [{'property': 'og:description'}, {'name': 'description'}]:
        meta = soup.find('meta', attrs=attrs)
        if meta:
            content = clean_description(meta.get('content', ''))
            # Skip if the meta just repeats the title
            if len(content) > 20 and content.lower().strip() != title_stripped:
                return content[:260]

    # 2. Common content containers for Hebrew municipal/culture sites
    for sel in [
        '.field--name-body p',
        '.content p',
        'article p',
        '.event-description p', '.event-description',
        '.entry-content p',
        '#MainContent p',
        '.event-body p',
        'main p',
    ]:
        el = soup.select_one(sel)
        if el:
            txt = clean_description(el.get_text(separator=' ', strip=True))
            if len(txt) > 20 and txt.lower().strip() != title_stripped:
                return txt[:260]

    return ''


def enrich_descriptions(events, max_workers=14, timeout=9):
    """Parallel-fetch descriptions for events that don't have one yet."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    to_enrich = [e for e in events if not e.get('description') and e.get('url')]
    if not to_enrich:
        return events

    print(f'  מוסיף תיאורים ל-{len(to_enrich)} אירועים...', file=sys.stderr, flush=True)

    def fetch_one(ev):
        desc = fetch_event_description(ev['url'], title=ev.get('title', ''), timeout=timeout)
        if desc:
            ev['description'] = desc

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(fetch_one, to_enrich, timeout=120))

    enriched = sum(1 for e in to_enrich if e.get('description'))
    print(f'    ✓ {enriched}/{len(to_enrich)} תיאורים נוספו', file=sys.stderr, flush=True)
    return events


# ─── City scrapers ───────────────────────────────────────────────────────────

def scrape_ganeytikva():
    """גני תקווה עירייה — ganeytikva.org.il/events/ (HTML)"""
    city = 'גני תקווה'
    base = 'https://www.ganeytikva.org.il'
    events = []

    soup = fetch(f'{base}/events/')
    if not soup:
        return events

    events_wrap = soup.select_one('div.content.events')
    if not events_wrap:
        events_wrap = soup.select_one('.events-wrap, [class*="event"]')

    items = events_wrap.select('div.event') if events_wrap else soup.select('div.event')

    for item in items:
        title_el = item.select_one('div.title, .event-title, h2, h3')
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        link_el = item.select_one('a.read_more, a[href]')
        link = ''
        if link_el:
            link = link_el.get('href', '')
            if link and not link.startswith('http'):
                link = urljoin(base + '/', link)

        cat_el = item.select_one('div.category, .category')
        category = cat_el.get_text(strip=True) if cat_el else ''

        date_divs = item.select('div.date div, div[class="date"] div')
        day = date_divs[0].get_text(strip=True) if date_divs else ''
        month = date_divs[1].get_text(strip=True) if len(date_divs) > 1 else ''
        date_text = f'{day} {month}'.strip()

        is_child, score = is_children_event(title, '', category)
        if is_child:
            events.append(make_event(city, title, None, date_text, link or f'{base}/events/', '', category, '', score))

    return events


def scrape_kiryatono():
    """קריית אונו עירייה — JSON API"""
    city = 'קריית אונו'
    base = 'https://www.kiryatono.muni.il'
    events = []

    data = fetch_json(f'{base}/events/json/?t={int(time.time())}')
    if not data or not isinstance(data, list):
        return events

    for ev in data:
        if ev.get('cancelled'):
            continue
        title = ev.get('title', '')
        if not title:
            continue
        start = ev.get('start', '')
        url = ev.get('url', '')
        if url and not url.startswith('http'):
            url = urljoin(base + '/', url)

        category = str(ev.get('category', ''))
        location = ev.get('locationName', '')

        is_child, score = is_children_event(title, location, category)
        if is_child:
            events.append(make_event(city, title, start, start, url or f'{base}/events/', location, category, '', score))

    return events


def scrape_hamatnas():
    """מתנ״ס קריית אונו — hamatnas.co.il (HTML, links to SmartTicket)"""
    city = 'קריית אונו'
    base = 'https://www.hamatnas.co.il'
    events = []

    soup = fetch(f'{base}/events/')
    if not soup:
        return events

    for item in soup.find_all('a', href=re.compile(r'smarticket|/event')):
        title_el = item.find(['h3', 'h2', 'h4'])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        url = item.get('href', f'{base}/events/')
        if url and not url.startswith('http'):
            url = urljoin(base, url)

        all_text = item.get_text(' ', strip=True)
        date_match = re.search(r'\d{1,2}[./]\d{1,2}[./]\d{4}', all_text)
        date_text = date_match.group(0) if date_match else ''

        img = item.find('img')
        image = ''
        if img:
            src = img.get('src', '')
            image = src if src.startswith('http') else urljoin(base, src)

        is_child, score = is_children_event(title)
        if is_child:
            events.append(make_event(city, title, None, date_text, url, '', '', '', score, image=image))

    return events


def scrape_savyon():
    """סביון עירייה — JSON API"""
    city = 'סביון'
    base = 'https://savyon.muni.il'
    events = []

    data = fetch_json(f'{base}/events/json/')
    if not data:
        soup = fetch(f'{base}/')
        if not soup:
            return events
        for item in soup.select('div.event, .event-item, article'):
            title_el = item.select_one('div.title, h2, h3, h4')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link_el = item.find('a', href=True)
            link = urljoin(base, link_el['href']) if link_el else base
            is_child, score = is_children_event(title)
            if is_child:
                events.append(make_event(city, title, None, '', link, '', '', '', score))
        return events

    if isinstance(data, dict):
        data = data.get('events', data.get('items', []))

    for ev in data:
        title = ev.get('title', '')
        if not title:
            continue
        start = ev.get('start', '')
        url = ev.get('url', '')
        if url and not url.startswith('http'):
            url = urljoin(base + '/', url)

        is_child, score = is_children_event(title, ev.get('locationName', ''))
        if is_child:
            events.append(make_event(city, title, start, start, url or f'{base}/', '', '', '', score))

    return events


def scrape_oryehuda():
    """אור יהודה עירייה — HTML"""
    city = 'אור יהודה'
    base = 'https://www.oryehuda.muni.il'
    events = []

    soup = fetch(f'{base}/events/')
    if not soup:
        return events

    items = (
        soup.select('article') or
        soup.select('div.event, .event-item, .event-card') or
        soup.select('[class*="event"]') or
        []
    )

    for item in items:
        title_el = (
            item.select_one('h2 a, h3 a, h4 a') or
            item.select_one('h2, h3, h4') or
            item.select_one('.title, .event-title')
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        link_el = (title_el if title_el.name == 'a'
                   else title_el.find('a')
                   or item.find('a', href=re.compile(r'/event|/\d{3,5}/')))
        link = ''
        if link_el and link_el.get('href'):
            link = urljoin(base, link_el['href'])

        date_el = item.select_one('time, [class*="date"], [datetime]')
        date_text = ''
        if date_el:
            date_text = date_el.get('datetime', '') or date_el.get_text(strip=True)
        if not date_text:
            m = re.search(r'\d{1,2}[./]\d{1,2}[./]\d{4}', item.get_text())
            if m:
                date_text = m.group(0)

        full_text = item.get_text()
        audience_m = re.search(r'קהל\s*יעד[:\s]+([^\n\r]{2,40})', full_text)
        audience = audience_m.group(1).strip() if audience_m else ''

        cat_els = item.select('[class*="cat"], a[rel="category"]')
        category = ' '.join(el.get_text(strip=True) for el in cat_els)

        is_child, score = is_children_event(title, full_text[:300], category, audience)
        if is_child:
            events.append(make_event(city, title, None, date_text, link or f'{base}/events/', '', category, audience, score))

    return events


def scrape_nifgashim():
    """נפגשים – מרכז קהילתי אור יהודה — nifgashim.org.il (HTML, links to SmartTicket)"""
    city = 'אור יהודה'
    base = 'https://nifgashim.org.il'
    events = []

    soup = fetch(f'{base}/events/')
    if not soup:
        return events

    for item in soup.find_all('a', href=re.compile(r'smarticket|/show|/event')):
        title_el = item.find(['h3', 'h2', 'h4'])
        if not title_el:
            raw = item.get_text(strip=True)
            if len(raw) < 5 or len(raw) > 100:
                continue
            title = raw
        else:
            title = title_el.get_text(strip=True)

        if not title:
            continue

        url = item.get('href', f'{base}/events/')
        if url and not url.startswith('http'):
            url = urljoin(base, url)

        all_text = item.get_text(' ', strip=True)
        date_match = re.search(r'\d{1,2}[./]\d{1,2}[./]\d{4}', all_text)
        date_text = date_match.group(0) if date_match else ''

        img = item.find('img')
        image = ''
        if img:
            src = img.get('src', '')
            image = src if src.startswith('http') else urljoin(base, src)

        is_child, score = is_children_event(title)
        if is_child:
            events.append(make_event(city, title, None, date_text, url, '', '', '', score, image=image))

    return events


def scrape_yehud():
    """יהוד-מונוסון — JSON מוטמע ב-data-events"""
    city = 'יהוד'
    base = 'https://yehud-monosson.muni.il'
    events = []
    CHILDREN_DEPTS = {6, 7, 88, 117, 128, 132, 133, 134}
    today = date.today()

    try:
        r = requests.get(
            f'{base}/%D7%9C%D7%95%D7%97-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/',
            headers=HEADERS, timeout=22
        )
        r.encoding = 'utf-8'
        html = r.text

        m = re.search(r'class="calendar-data"\s+data-events="(\[.*?\])"', html, re.DOTALL)
        if not m:
            return events

        raw_json = html_mod.unescape(m.group(1))
        all_events = jsonlib.loads(raw_json)

        for ev in all_events:
            title = ev.get('title', '').strip()
            if not title:
                continue
            start = ev.get('start', '')
            ev_date = parse_date(start)
            if ev_date and ev_date < today:
                continue

            url = ev.get('url', '') or f'{base}/events/'
            dept = ev.get('department_id')
            description = ev.get('description', '') or ''
            if isinstance(description, dict):
                description = str(description)
            if description.strip().lower() in ('description', 'none', ''):
                description = ''

            is_child, score = is_children_event(title, description[:200])
            in_core_dept = dept == 7
            in_child_dept = dept in CHILDREN_DEPTS

            if not in_core_dept and not is_child:
                continue
            if not in_child_dept and not is_child:
                continue
            if in_core_dept and score == 0:
                score = 2

            cat_val = str(dept or '')
            ev = make_event(city, title, ev_date, start, url, description[:200], cat_val, '', score)
            # Dept-based age hint when text extraction finds nothing
            if not ev['age_label']:
                if dept == 7:
                    ev['age_label'] = 'גיל הרך'
                elif dept == 6:
                    ev['age_label'] = 'משפחות'
            events.append(ev)

    except Exception as e:
        print(f'  יהוד שגיאה: {e}', file=sys.stderr)

    return events


def scrape_petahtikva():
    """פתח תקווה — האתר חסום; מחזיר פריט הפניה"""
    return [{
        'city': 'פתח תקווה',
        'title': '📍 לאירועי פתח תקווה — לחצי לאתר העירייה',
        'date': None,
        'date_text': '',
        'url': 'https://www.petah-tikva.muni.il/events',
        'description': 'האתר חוסם סריקה אוטומטית. לחצי כאן לצפות ישירות בלוח האירועים.',
        'category': 'קישור ידני',
        'audience': '',
        'score': 0,
        'special': False,
        'image': '',
    }]


# ─── Special events scraper ───────────────────────────────────────────────────

def scrape_habama_special():
    """מרכז הבמה – הצגות ואירועים לילדים ברחבי המרכז (habama.co.il)"""
    base = 'https://www.habama.co.il'
    events = []
    today = date.today()
    seen_titles = set()

    # Children's events page (Subj=6 = ילדים, Area=1 = מרכז)
    soup = fetch(f'{base}/Pages/SubjectCategory.aspx?Subj=6&Area=1', timeout=20)
    if not soup:
        return events

    for a in soup.find_all('a', href=re.compile(r'EventID=\d+')):
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)

        href = a.get('href', '')
        url = href if href.startswith('http') else f'{base}{href}'

        # Navigate up to table row for date/venue
        row = a.find_parent('tr')
        date_text = ''
        venue = ''
        if row:
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            for cell in cells:
                if cell == title:
                    continue
                if re.search(r'\d{1,2}[./]\d{1,2}', cell) and not date_text:
                    date_text = cell
                elif cell and len(cell) > 2 and not venue:
                    venue = cell

        ev_date = parse_date(date_text)
        if ev_date and ev_date < today:
            continue

        # Try to find image near the link
        img = a.find_parent('td')
        image = ''
        if img:
            img_el = img.find_previous('img') or img.find_next('img')
            if img_el:
                src = img_el.get('src', '')
                if src:
                    image = src if src.startswith('http') else f'{base}{src}'

        ev = make_event(
            'מיוחד', title, ev_date, date_text, url,
            venue, 'הצגת ילדים', '', 5,
            special=True, image=image
        )
        if not ev['age_label']:
            ev['age_label'] = 'ילדים'
        events.append(ev)

    return events


# ─── HTML generator ───────────────────────────────────────────────────────────

def generate_html(city_events, special_events, city_stats):
    today = date.today()
    today_iso = today.isoformat()
    update_str = today.strftime('%d.%m.%Y')

    # ── Sort city events ──
    dated = sorted(
        [e for e in city_events if e['date'] and e['date'] >= today],
        key=lambda e: (e['date'], -e['score'])
    )
    no_date = [e for e in city_events if not e['date']]

    # ── Sort special events ──
    spec_dated = sorted(
        [e for e in special_events if e['date'] and e['date'] >= today],
        key=lambda e: e['date']
    )
    spec_nodate = [e for e in special_events if not e['date']]
    all_special = spec_dated + spec_nodate

    # Compute special event type sub-tabs
    TYPE_ORDER = ['הצגות', 'פסטיבלים', 'קייטנות', 'תערוכות', 'מוסיקה', 'סדנאות', 'ספרייה', 'ספורט', 'אחר']
    TYPE_ICONS = {
        'הצגות': '🎭', 'פסטיבלים': '🎪', 'קייטנות': '☀️',
        'תערוכות': '🖼️', 'מוסיקה': '🎵', 'סדנאות': '🎨',
        'ספרייה': '📚', 'ספורט': '⚽', 'אחר': '✨',
    }
    seen_types = set(e.get('event_type', 'אחר') for e in all_special)
    active_types = [t for t in TYPE_ORDER if t in seen_types]

    total_city = len(dated) + len(no_date)
    total_special = len(all_special)
    total_events = total_city + total_special

    # ── Card builder ──
    def card_html(ev):
        is_special = ev.get('special', False)
        color = '#c2410c' if is_special else CITY_COLORS.get(ev['city'], '#555')
        city_label = '⭐ מיוחד' if is_special else esc(ev['city'])
        event_type = ev.get('event_type', 'אחר')

        title_esc = esc(ev['title'])
        url_esc = esc(ev['url'])
        desc = ev.get('description', '')
        date_iso = ev['date'].isoformat() if ev['date'] else ''

        date_html = ''
        if ev['date']:
            date_html = f'<span class="ev-date">📅 {esc(format_date_display(ev["date"]))}</span>'

        age_html = ''
        if ev.get('age_label'):
            age_html = f'<span class="age-badge">👶 {esc(ev["age_label"])}</span>'

        type_html = ''
        if is_special and event_type and event_type != 'אחר':
            icon = TYPE_ICONS.get(event_type, '✨')
            type_html = f'<span class="type-badge">{icon} {esc(event_type)}</span>'

        image_html = ''
        if ev.get('image'):
            image_html = f'<img class="ev-img" src="{esc(ev["image"])}" alt="" loading="lazy" onerror="this.style.display=\'none\'">'

        # Build display description — always show something
        display_desc = desc
        if not display_desc:
            # For special events: try to parse venue from "Title - Venue" pattern
            if is_special:
                m = re.search(r'[-–]\s*([^\-–]{4,35})\s*$', ev['title'])
                if m:
                    potential = m.group(1).strip()
                    venue_kw = ['תיאטרון', 'בית', 'אולם', 'מרכז', 'קניון', 'פארק', 'גלריה', 'מוזיאון', 'היכל']
                    if any(w in potential for w in venue_kw):
                        display_desc = potential
            # For city events: use category/audience
            if not display_desc:
                parts = [p.strip() for p in [ev.get('category', ''), ev.get('audience', '')] if p and p.strip()]
                if parts:
                    display_desc = ' · '.join(parts)
            # Last resort: use event type
            if not display_desc and event_type and event_type != 'אחר':
                display_desc = event_type

        desc_html = ''
        if is_special and display_desc:
            desc_html = f'<div class="ev-venue">📍 {esc(display_desc[:140])}</div>'
        elif display_desc:
            trimmed = display_desc[:240] + ('…' if len(display_desc) > 240 else '')
            desc_html = f'<div class="ev-desc">{esc(trimmed)}</div>'

        type_data = esc(event_type)
        city_data = esc(ev['city'])
        card_cls = 'card special-card' if is_special else 'card'
        return f'''<div class="{card_cls}" data-city="{city_data}" data-date="{date_iso}" data-type="{type_data}">
  {image_html}
  <div class="card-body">
    <div class="card-top">
      <span class="city-badge" style="background:{color}">{city_label}</span>
      {age_html}{type_html}
      <span class="flex-gap"></span>
      {date_html}
    </div>
    <h3 class="ev-title"><a href="{url_esc}" target="_blank" rel="noopener">{title_esc}</a></h3>
    {desc_html}
    <div class="card-footer">
      <a class="btn-link" href="{url_esc}" target="_blank" rel="noopener">פרטים והרשמה ←</a>
    </div>
  </div>
</div>'''

    # ── Special events section ──
    special_section = ''
    if all_special:
        stabs = (f'<button class="stab active" onclick="filterType(this,\'all\')">'
                 f'הכל <span class="stab-count">{total_special}</span></button>\n')
        for t in active_types:
            icon = TYPE_ICONS.get(t, '✨')
            cnt = sum(1 for e in all_special if e.get('event_type', 'אחר') == t)
            stabs += (f'<button class="stab" onclick="filterType(this,\'{t}\')">'
                      f'{icon} {esc(t)} <span class="stab-count">{cnt}</span></button>\n')

        cards = '\n'.join(card_html(ev) for ev in all_special)
        special_section = f'''<details class="section-wrap" open>
  <summary class="section-hdr">
    <span class="section-hdr-left"><span class="sicon">⭐</span> אירועים מיוחדים</span>
    <span class="section-pill" style="background:#c2410c">{total_special}</span>
  </summary>
  <div class="special-type-tabs">{stabs}</div>
  <div class="special-grid" id="specialGrid">
{cards}
  </div>
</details>'''

    # ── City events section ──
    city_inner = ''
    current_date_label = None
    for ev in dated:
        d_label = format_date_display(ev['date'])
        if d_label != current_date_label:
            if current_date_label:
                city_inner += '</div>\n'
            current_date_label = d_label
            city_inner += (f'<div class="date-group">\n'
                           f'<div class="date-header">{esc(d_label)}</div>\n')
        city_inner += card_html(ev) + '\n'
    if current_date_label:
        city_inner += '</div>\n'

    if no_date:
        city_inner += '<div class="date-group">\n<div class="date-header undated">ללא תאריך</div>\n'
        for ev in no_date:
            city_inner += card_html(ev) + '\n'
        city_inner += '</div>\n'

    city_section = ''
    if city_inner:
        city_section = f'''<details class="section-wrap" open>
  <summary class="section-hdr">
    <span class="section-hdr-left"><span class="sicon">📍</span> אירועים עירוניים</span>
    <span class="section-pill" style="background:#0d9488">{total_city}</span>
  </summary>
  <div class="city-events-inner">
{city_inner}
  </div>
</details>'''

    # ── City tabs ──
    tabs_html = (f'<button class="tab active" onclick="filterCity(this,\'הכל\')" style="--c:#0d9488">'
                 f'הכל <span class="tab-count">{total_city}</span></button>\n')
    for city in sorted(set(e['city'] for e in city_events)):
        if city == 'פתח תקווה' and city_stats.get(city, 0) == 0:
            continue
        color = CITY_COLORS.get(city, '#555')
        count = city_stats.get(city, 0)
        tabs_html += (f'<button class="tab" onclick="filterCity(this,\'{city}\')" style="--c:{color}">'
                      f'{esc(city)} <span class="tab-count">{count}</span></button>\n')

    # ── Stats chips ──
    stats_html = ''
    for city, count in sorted(city_stats.items()):
        if count == 0:
            continue
        color = CITY_COLORS.get(city, '#555')
        stats_html += (f'<span class="stat-chip" style="--c:{color}">'
                       f'<span class="dot"></span>{esc(city)}: {count}</span>')

    return f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎈 אירועים לילדים – ערי המרכז</title>
<style>
/* ── Reset & tokens ── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  /* Neutral base */
  --bg:       #f4f2ee;
  --surface:  #ffffff;
  --surface2: #f9f8f5;
  --border:   #e2dbd3;
  --text:     #1a1511;
  --text2:    #6b5e53;
  --text3:    #a89789;
  /* Action blue — links & general buttons */
  --primary:  #1d4ed8;
  --primary-h:#1e40af;
  /* Teal — city section, date filters */
  --city:     #0d9488;
  --city-h:   #0f766e;
  /* Orange — special events section */
  --special:  #c2410c;
  --special-h:#9a3412;
  /* Shadows */
  --shadow:   0 1px 5px rgba(26,21,17,.06), 0 3px 10px rgba(26,21,17,.04);
  --shadow-h: 0 4px 16px rgba(26,21,17,.12);
  --radius:   12px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #141210; --surface: #1e1b18; --surface2: #141210;
    --border: #302a24; --text: #f0ebe4; --text2: #9a8c7e; --text3: #5a5048;
    --primary: #60a5fa; --primary-h: #93c5fd;
    --city: #2dd4bf; --city-h: #5eead4;
    --special: #fb923c; --special-h: #fdba74;
    --shadow: 0 2px 10px rgba(0,0,0,.5); --shadow-h: 0 5px 22px rgba(0,0,0,.65);
  }}
}}
:root[data-theme="dark"] {{
  --bg: #141210; --surface: #1e1b18; --surface2: #141210;
  --border: #302a24; --text: #f0ebe4; --text2: #9a8c7e; --text3: #5a5048;
  --primary: #60a5fa; --primary-h: #93c5fd;
  --city: #2dd4bf; --city-h: #5eead4;
  --special: #fb923c; --special-h: #fdba74;
  --shadow: 0 2px 10px rgba(0,0,0,.5); --shadow-h: 0 5px 22px rgba(0,0,0,.65);
}}
:root[data-theme="light"] {{
  --bg: #f4f2ee; --surface: #ffffff; --surface2: #f9f8f5;
  --border: #e2dbd3; --text: #1a1511; --text2: #6b5e53; --text3: #a89789;
  --primary: #1d4ed8; --primary-h: #1e40af;
  --city: #0d9488; --city-h: #0f766e;
  --special: #c2410c; --special-h: #9a3412;
  --shadow: 0 1px 5px rgba(26,21,17,.06), 0 3px 10px rgba(26,21,17,.04);
  --shadow-h: 0 4px 16px rgba(26,21,17,.12);
}}

body {{
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  direction: rtl;
  min-height: 100vh;
}}

/* ── Header ── */
header {{
  background: linear-gradient(135deg, #1e1b4b 0%, #1e40af 40%, #0d9488 75%, #065f46 100%);
  color: #fff;
  padding: 1.8rem 1.5rem 1.4rem;
  text-align: center;
}}
header h1 {{ font-size: clamp(1.5rem, 5vw, 2rem); font-weight: 800; letter-spacing: -.4px; }}
.subtitle {{ opacity: .72; font-size: .85rem; margin-top: .3rem; }}
.update-line {{ margin-top: .6rem; font-size: .74rem; opacity: .52; }}
.stats-bar {{ display: flex; flex-wrap: wrap; gap: .35rem; justify-content: center; margin-top: .9rem; }}
.stat-chip {{
  display: inline-flex; align-items: center; gap: .3rem;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.18);
  border-radius: 20px; padding: .15rem .58rem; font-size: .72rem; color: rgba(255,255,255,.88);
}}
.stat-chip .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--c,#9cf); flex-shrink:0; }}

/* ── Sticky filter bar ── */
.filter-bar {{
  position: sticky; top: 0; z-index: 50;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow);
  padding: .5rem 1rem;
}}
.filter-inner {{ max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: .4rem; }}
.search-wrap {{ position: relative; }}
.search-wrap input {{
  width: 100%; padding: .42rem .9rem .42rem 2.1rem;
  border: 1.5px solid var(--border); border-radius: 24px;
  background: var(--surface2); color: var(--text);
  font-size: .88rem; font-family: var(--font);
  outline: none; transition: border-color .15s;
}}
.search-wrap input:focus {{ border-color: var(--primary); }}
.search-wrap::before {{
  content: "🔍"; position: absolute; left: .7rem; top: 50%;
  transform: translateY(-50%); font-size: .8rem; pointer-events: none;
}}
/* Quick date filters */
.quick-filters, .tabs {{
  display: flex; gap: .3rem; overflow-x: auto;
  padding-bottom: 2px; scrollbar-width: none;
}}
.quick-filters::-webkit-scrollbar, .tabs::-webkit-scrollbar {{ display: none; }}
.qf, .tab {{
  flex-shrink: 0;
  background: var(--surface2); border: 1.5px solid var(--border);
  color: var(--text2); border-radius: 20px;
  padding: .24rem .7rem; font-size: .78rem; font-family: var(--font);
  cursor: pointer; transition: all .13s; white-space: nowrap;
}}
.qf:hover {{ border-color: var(--city); color: var(--text); }}
.qf.active {{ background: var(--city); border-color: var(--city); color: #fff; font-weight: 600; }}
.tab:hover {{ border-color: var(--c, var(--city)); color: var(--text); }}
.tab.active {{ background: var(--c, var(--city)); border-color: var(--c, var(--city)); color: #fff; font-weight: 600; }}
.tab-count, .stab-count {{ opacity: .68; font-size: .72em; font-weight: 400; }}

/* ── Theme toggle ── */
.theme-toggle {{
  position: fixed; bottom: 1.1rem; left: 1.1rem; z-index: 100;
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--surface); border: 1.5px solid var(--border);
  box-shadow: var(--shadow); cursor: pointer;
  font-size: 1rem; display: grid; place-items: center;
  transition: box-shadow .15s;
}}
.theme-toggle:hover {{ box-shadow: var(--shadow-h); }}

/* ── Main ── */
main {{
  max-width: 900px; margin: 0 auto;
  padding: 1rem 1rem 5rem;
}}
.count-bar {{
  font-size: .78rem; color: var(--text2);
  margin-bottom: .9rem; text-align: center;
}}

/* ── Collapsible sections ── */
.section-wrap {{
  margin-bottom: 1.4rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
  overflow: hidden;
}}
.section-wrap > summary {{ list-style: none; }}
.section-wrap > summary::-webkit-details-marker {{ display: none; }}
.section-hdr {{
  display: flex; align-items: center; justify-content: space-between;
  padding: .8rem 1.1rem;
  cursor: pointer; user-select: none;
  border-bottom: 1px solid var(--border);
  transition: background .12s;
}}
.section-hdr:hover {{ background: var(--surface2); }}
.section-hdr-left {{ display: flex; align-items: center; gap: .45rem; font-size: .95rem; font-weight: 700; color: var(--text); }}
.sicon {{ font-size: 1rem; }}
.section-pill {{
  background: var(--primary); color: #fff;
  border-radius: 12px; padding: .13rem .52rem;
  font-size: .7rem; font-weight: 700; flex-shrink: 0;
}}
/* Sub-tabs for special event types */
.special-type-tabs {{
  display: flex; gap: .28rem; overflow-x: auto;
  padding: .55rem 1rem; border-bottom: 1px solid var(--border);
  background: var(--surface2); scrollbar-width: none;
}}
.special-type-tabs::-webkit-scrollbar {{ display: none; }}
.stab {{
  flex-shrink: 0;
  background: transparent; border: 1.5px solid var(--border);
  color: var(--text2); border-radius: 20px;
  padding: .2rem .6rem; font-size: .76rem; font-family: var(--font);
  cursor: pointer; transition: all .13s; white-space: nowrap;
}}
.stab:hover {{ border-color: var(--special); color: var(--text); }}
.stab.active {{ background: var(--special); border-color: var(--special); color: #fff; font-weight: 600; }}

/* Section body */
.special-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(255px, 1fr));
  gap: .75rem;
  padding: .85rem 1rem 1rem;
}}
.city-events-inner {{ padding: .6rem 1rem 1rem; }}

/* ── Date headers ── */
.date-group {{ margin-bottom: .2rem; }}
.date-header {{
  display: flex; align-items: center; gap: .45rem;
  font-size: .87rem; font-weight: 700; color: var(--city);
  padding: .35rem .5rem;
  margin: .9rem 0 .45rem;
}}
.date-header::before {{
  content: ''; display: inline-block;
  width: 3px; height: 15px; background: var(--city); border-radius: 2px; flex-shrink: 0;
}}
.date-header.undated {{ color: var(--text2); }}
.date-header.undated::before {{ background: var(--text3); }}

/* ── Cards ── */
.card {{
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border);
  margin-bottom: .55rem;
  box-shadow: var(--shadow);
  overflow: hidden;
  transition: box-shadow .17s, transform .17s;
}}
.card:hover {{ box-shadow: var(--shadow-h); transform: translateY(-1px); }}
.special-card {{ display: flex; flex-direction: column; border-color: rgba(217,119,6,.25); margin-bottom: 0; }}
.special-card:hover {{ border-color: var(--special); }}
.ev-img {{ width: 100%; height: 155px; object-fit: cover; display: block; background: var(--surface2); }}

/* ── Card body ── */
.card-body {{ padding: .8rem .95rem; flex: 1; display: flex; flex-direction: column; }}
.card-top {{
  display: flex; align-items: center; flex-wrap: wrap;
  gap: .3rem; margin-bottom: .45rem;
}}
.flex-gap {{ flex: 1; min-width: .3rem; }}
.city-badge {{
  color: #fff; font-size: .64rem; font-weight: 700;
  padding: .14rem .48rem; border-radius: 9px; letter-spacing: .2px; flex-shrink: 0;
}}
.ev-date {{ font-size: .74rem; color: var(--text2); white-space: nowrap; }}

/* Age badge — forest green */
.age-badge {{
  display: inline-flex; align-items: center; gap: .15rem;
  background: #f0fdf4; border: 1.5px solid #16a34a;
  color: #15803d; border-radius: 20px;
  padding: .12rem .45rem; font-size: .67rem; font-weight: 700; flex-shrink: 0;
}}
@media (prefers-color-scheme: dark) {{
  .age-badge {{ background: #052e16; border-color: #16a34a; color: #4ade80; }}
}}
:root[data-theme="dark"] .age-badge {{ background: #052e16; border-color: #16a34a; color: #4ade80; }}
:root[data-theme="light"] .age-badge {{ background: #f0fdf4; border-color: #16a34a; color: #15803d; }}

/* Event type badge — amber */
.type-badge {{
  display: inline-flex; align-items: center; gap: .15rem;
  background: #fffbeb; border: 1.5px solid #d97706;
  color: #92400e; border-radius: 20px;
  padding: .12rem .45rem; font-size: .67rem; font-weight: 600; flex-shrink: 0;
}}
@media (prefers-color-scheme: dark) {{
  .type-badge {{ background: #1c1003; border-color: #d97706; color: #fde68a; }}
}}
:root[data-theme="dark"] .type-badge {{ background: #1c1003; border-color: #d97706; color: #fde68a; }}
:root[data-theme="light"] .type-badge {{ background: #fffbeb; border-color: #d97706; color: #92400e; }}

.ev-title {{ font-size: .96rem; font-weight: 700; line-height: 1.4; margin-bottom: .32rem; }}
.ev-title a {{ color: var(--text); text-decoration: none; }}
.ev-title a:hover {{ color: var(--primary); text-decoration: underline; }}
.ev-venue {{ font-size: .78rem; color: var(--text2); margin-bottom: .28rem; }}
.ev-desc {{
  font-size: .81rem; color: var(--text2); line-height: 1.55;
  margin-bottom: .4rem; flex: 1;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}}
.card-footer {{ display: flex; align-items: center; margin-top: auto; padding-top: .35rem; }}
.btn-link {{
  display: inline-block;
  background: var(--primary); color: #fff;
  padding: .28rem .78rem; border-radius: 8px;
  font-size: .75rem; font-weight: 700;
  text-decoration: none;
  transition: background .13s;
}}
.btn-link:hover {{ background: var(--primary-h); }}
.special-card .btn-link {{ background: var(--special); color: #fff; }}
.special-card .btn-link:hover {{ background: var(--special-h); }}

/* ── Hidden / empty ── */
.card.hidden, .date-group.hidden {{ display: none; }}
.empty-state {{ text-align: center; padding: 3rem 1rem; color: var(--text2); font-size: .95rem; }}

/* ── Mobile ── */
@media (max-width: 560px) {{
  header {{ padding: 1.3rem .9rem 1.1rem; }}
  .special-grid {{ grid-template-columns: 1fr; }}
  .card-body {{ padding: .7rem .8rem; }}
  .section-hdr {{ padding: .65rem .85rem; }}
}}
</style>
</head>
<body>

<header>
  <h1>🎈 אירועים לילדים</h1>
  <p class="subtitle">גני תקווה &middot; קריית אונו &middot; פתח תקווה &middot; סביון &middot; אור יהודה &middot; יהוד</p>
  <p class="update-line">מתעדכן אוטומטית כל יום 🔄 &nbsp;|&nbsp; עודכן: {update_str}</p>
  <div class="stats-bar">{stats_html}</div>
</header>

<div class="filter-bar">
  <div class="filter-inner">
    <div class="search-wrap">
      <input type="search" id="searchInput" placeholder="חפשי אירוע, הצגה, תאריך..." oninput="onSearch(this.value)">
    </div>
    <div class="quick-filters" id="quickFilters">
      <button class="qf active" onclick="filterPeriod(this,\'all\')">כל התאריכים</button>
      <button class="qf" onclick="filterPeriod(this,\'today\')">היום</button>
      <button class="qf" onclick="filterPeriod(this,\'week\')">השבוע</button>
      <button class="qf" onclick="filterPeriod(this,\'month\')">החודש הקרוב</button>
    </div>
    <div class="tabs" id="cityTabs">
      {tabs_html}
    </div>
  </div>
</div>

<main>
  <p class="count-bar" id="countBar">{total_events} אירועים נמצאו</p>
  {special_section}
  {city_section}
  <div class="empty-state" id="emptyState" style="display:none">
    לא נמצאו אירועים התואמים את הסינון 🔍
  </div>
</main>

<button class="theme-toggle" id="themeToggle" title="החלפת ערכת צבעים" onclick="toggleTheme()">🌙</button>

<script>
// ── Theme ──
(function() {{
  var saved = localStorage.getItem('theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  updateToggleIcon();
}})();
function toggleTheme() {{
  var cur = document.documentElement.getAttribute('data-theme');
  var next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateToggleIcon();
}}
function updateToggleIcon() {{
  var t = document.getElementById('themeToggle');
  if (t) t.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
}}

// ── Filter state ──
var activeCity = 'הכל';
var activePeriod = 'all';
var activeType = 'all';
var searchQuery = '';
var todayStr = '{today_iso}';

function filterCity(btn, city) {{
  activeCity = city;
  document.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});
  btn.classList.add('active');
  applyFilters();
}}
function filterPeriod(btn, period) {{
  activePeriod = period;
  document.querySelectorAll('.qf').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  applyFilters();
}}
function filterType(btn, type) {{
  activeType = type;
  document.querySelectorAll('.stab').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  applyFilters();
}}
function onSearch(val) {{
  searchQuery = val.trim().toLowerCase();
  applyFilters();
}}

function applyFilters() {{
  var wkEnd = new Date(todayStr); wkEnd.setDate(wkEnd.getDate() + 7);
  var moEnd = new Date(todayStr); moEnd.setDate(moEnd.getDate() + 30);
  var vis = 0;

  document.querySelectorAll('.card').forEach(function(card) {{
    var isSpec = card.classList.contains('special-card');

    // City filter: only city events; special events are always shown across cities
    var cityOk = isSpec || activeCity === 'הכל' || card.dataset.city === activeCity;

    // Date filter: applies to both; undated cards hidden when period selected
    var ds = card.dataset.date;
    var dateOk = true;
    if (activePeriod !== 'all') {{
      if (!ds) {{
        dateOk = false;
      }} else {{
        var d = new Date(ds);
        if (activePeriod === 'today') dateOk = ds === todayStr;
        else if (activePeriod === 'week') dateOk = d <= wkEnd;
        else if (activePeriod === 'month') dateOk = d <= moEnd;
      }}
    }}

    // Type filter: only special events
    var typeOk = !isSpec || activeType === 'all' || (card.dataset.type || '') === activeType;

    // Text search: across all cards
    var txtOk = !searchQuery || card.textContent.toLowerCase().includes(searchQuery);

    var show = cityOk && dateOk && typeOk && txtOk;
    card.classList.toggle('hidden', !show);
    if (show) vis++;
  }});

  // Hide empty date groups
  document.querySelectorAll('.date-group').forEach(function(g) {{
    g.classList.toggle('hidden', g.querySelectorAll('.card:not(.hidden)').length === 0);
  }});

  var cb = document.getElementById('countBar');
  if (cb) cb.textContent = vis + ' אירועים נמצאו';
  var es = document.getElementById('emptyState');
  if (es) es.style.display = vis === 0 ? 'block' : 'none';
}}
</script>
</body>
</html>'''


# ─── Main ────────────────────────────────────────────────────────────────────

CITY_SCRAPERS = [
    ('גני תקווה',  scrape_ganeytikva),
    ('קריית אונו', scrape_kiryatono),
    ('קריית אונו', scrape_hamatnas),
    ('פתח תקווה',  scrape_petahtikva),
    ('סביון',      scrape_savyon),
    ('אור יהודה',  scrape_oryehuda),
    ('אור יהודה',  scrape_nifgashim),
    ('יהוד',       scrape_yehud),
]

SPECIAL_SCRAPERS = [
    scrape_habama_special,
]


def main():
    today = date.today()
    all_city = []
    all_special = []
    city_stats = {c: 0 for c in CITY_COLORS}

    # City scrapers
    for city, fn in CITY_SCRAPERS:
        print(f'סורק {city} ({fn.__name__})...', file=sys.stderr, flush=True)
        try:
            evs = fn()
            count = len(evs)
            print(f'  ✓ {count} אירועים', file=sys.stderr, flush=True)
            all_city.extend(evs)
            city_stats[city] = city_stats.get(city, 0) + count
        except Exception as e:
            print(f'  ✗ שגיאה: {e}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

    # Special scrapers
    for fn in SPECIAL_SCRAPERS:
        print(f'סורק אירועים מיוחדים ({fn.__name__})...', file=sys.stderr, flush=True)
        try:
            evs = fn()
            print(f'  ✓ {len(evs)} אירועים מיוחדים', file=sys.stderr, flush=True)
            all_special.extend(evs)
        except Exception as e:
            print(f'  ✗ שגיאה: {e}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

    # Sort & deduplicate city events
    all_city.sort(key=lambda e: (
        not (e['date'] and e['date'] >= today),
        e['date'] or date.max,
        -e['score'],
    ))
    seen = set()
    unique_city = []
    for e in all_city:
        key = (e['city'], e['title'][:40].strip(), str(e['date']))
        if key not in seen:
            seen.add(key)
            unique_city.append(e)

    # Deduplicate special events
    seen_spec = set()
    unique_special = []
    for e in all_special:
        key = (e['title'][:40].strip(), str(e['date']))
        if key not in seen_spec:
            seen_spec.add(key)
            unique_special.append(e)

    # Enrich descriptions by fetching each event's detail page
    print('\nמוסיף תיאורים לאירועים עירוניים...', file=sys.stderr, flush=True)
    enrich_descriptions(unique_city)
    print('מוסיף תיאורים לאירועים מיוחדים...', file=sys.stderr, flush=True)
    enrich_descriptions(unique_special)

    html = generate_html(unique_city, unique_special, city_stats)
    output = Path('index.html')
    output.write_text(html, encoding='utf-8')

    total = len(unique_city) + len(unique_special)
    with_desc = sum(1 for e in unique_city + unique_special if e.get('description'))
    print(f'\n✅ נשמר: {output}', file=sys.stderr)
    print(f'   {len(unique_city)} אירועים עירוניים + {len(unique_special)} מיוחדים = {total} סה"כ', file=sys.stderr)
    print(f'   {with_desc}/{total} עם תיאור', file=sys.stderr)

    # Open locally if running interactively
    import os
    if os.isatty(sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else 0):
        try:
            import subprocess
            subprocess.run(['open', str(output)])
        except Exception:
            pass


if __name__ == '__main__':
    main()
