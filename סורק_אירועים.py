#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
סורק אירועים לילדים (גיל 3-6) מאתרי עיריות המרכז:
גני תקווה, קריית אונו, פתח תקווה, סביון, אור יהודה, יהוד

הרצה: python3 סורק_אירועים.py
"""

import requests
from bs4 import BeautifulSoup
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
import time

# ─── הגדרות ───────────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'he,en-US;q=0.7,en;q=0.3',
}

HEBREW_MONTHS = {
    'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'מרס': 3, 'אפריל': 4,
    'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
}

CITY_COLORS = {
    'גני תקווה':   '#2E7D32',
    'קריית אונו':  '#1565C0',
    'פתח תקווה':  '#6A1B9A',
    'סביון':       '#E65100',
    'אור יהודה':   '#AD1457',
    'יהוד':        '#00695C',
}

# מילות מפתח חיוביות – אירוע לילדים / משפחות
CHILDREN_KEYWORDS = [
    'ילדים', 'ילד', 'ילדה', 'לילדים', 'לילד',
    'גיל הרך', 'פעוטות', 'פעוט', 'פעוטון',
    'משפחות', 'משפחה', 'לכל המשפחה', 'לכל המשפחות',
    'הורים וילדים', 'הורים ותינוקות', 'הורים ופעוטות',
    'עם הילדים', 'עם הילד', 'עם הילדה',
    'אמא ותינוק', 'אבא ותינוק', 'בוקר עם אבא', 'בוקר עם אמא',
    'הצגה', 'בובות', 'בובתיאטרון',
    'קטנטנים', 'גן ילדים', 'גני ילדים', 'גיל הגן',
    'תינוקות', 'תינוק', 'תינוקת',
    'קייטנ',  # קייטנה / קייטנות
    'תיאטרונויה',  # brand שמציג הצגות לילדים
    'מחזמר לילדים',
    'הרפתקה', 'הרפתקאות',
    'גיל 3', 'גיל 4', 'גיל 5', 'גיל 6',
    'גיל שלוש', 'גיל ארבע', 'גיל חמש',
    'לגיל', 'לגילאי', 'לגילאים',
    'ליווי התפתחותי', 'התפתחות הילד',
    'בייבי', 'baby',
    'קטנים', 'קטן', 'קטנה',
]

AGE_PATTERNS = [
    r'(?:גיל|לגילאי?|לגיל|לגילאים)\s*[2-7]',
    r'[2-7]\s*[-–]\s*[3-9]\s*(?:שנ|שנות|שנה)',
    r'(?:3|4|5|6)\s*[-–]\s*(?:5|6|7|8)',
    r'(?:ב)?גילאי?\s+(?:2|3|4|5|6)',
    r'גיל הרך',
    r'לכל המשפח',
    r'\bילדים\b',
    r'פעוט',
    r'תינוק',
    r'קייטנ',
    r'(?:לידה|זחילה|הליכה)\s+(?:עד|ועד)',  # developmental stages for babies
    r'(?:מ)?גיל\s+(?:אפס|0)',
    r'ב[׳\']\s*[-–]\s*ג[׳\']',  # grades bet-gimel (2nd-3rd grade, ages 7-9, still valid)
    r'א[׳\']\s*[-–]',  # grade aleph+
]

EXCLUDE_KEYWORDS = [
    'לנוער בלבד',
    'למבוגרים בלבד',
    'אזרחים ותיקים',
    'לסטודנטים',
    'לעסקים',
    'ותיקים',
    'קשישים',
    'בוגרים בלבד',
    'אולם פתוח בוגרים',
    'נוער בלבד',
]

ADULT_ONLY_PATTERNS = [
    r'(?:^|\s)(?:לבוגרים|למבוגרים|לנשים|לגברים|לזוגות|לאבות|לאמהות)(?:\s|$)',
    r'ריתוך|溶接',
    r'(?:^|\s)סדנת\s+(?:כתיבה|צילום|יין|בישול\s+מתקדם)(?:\s|$)',
    r'(?:^|\s)(?:ערב\s+זול|בר\s+מצוה|בת\s+מצוה)(?:\s|$)',
    r'לנוער\s+(?:בלבד|18|16)',
    r'אולם פתוח בוגרים',
]


# ─── פונקציות עזר ──────────────────────────────────────────────────────────────

def fetch(url, timeout=18):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = 'utf-8'
        return BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        print(f"  ⚠  שגיאה בטעינת {url}: {e}", file=sys.stderr)
        return None


def fetch_json(url, timeout=12):
    try:
        r = requests.get(url, headers={**HEADERS, 'Accept': 'application/json'}, timeout=timeout)
        r.encoding = 'utf-8'
        return r.json()
    except Exception as e:
        print(f"  ⚠  JSON שגיאה {url}: {e}", file=sys.stderr)
        return None


def parse_date(text):
    if not text:
        return None
    text = str(text).strip()
    today = date.today()

    # ISO: 2026-07-20 or 2026-07-20T09:00:00
    m = re.search(r'(202\d)[-/](\d{2})[-/](\d{2})', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # DD/MM/YYYY or DD.MM.YYYY
    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # Hebrew month name
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
    return f"יום {DAY_NAMES[d.weekday()]}, {d.day} ב{MONTH_NAMES[d.month]} {d.year}"


def is_children_event(title, description='', category='', audience=''):
    combined = f"{title} {description} {category} {audience}"
    for excl in EXCLUDE_KEYWORDS:
        if excl in combined:
            return False, 0
    for pattern in ADULT_ONLY_PATTERNS:
        if re.search(pattern, combined):
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
    """Remove HTML tags and normalize whitespace from description text"""
    if not text:
        return ''
    import html as html_mod
    text = html_mod.unescape(str(text))
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Skip literal placeholder values
    if text.lower() in ('description', 'none'):
        return ''
    return text[:250]


def make_event(city, title, date_val, date_text, url, description='', category='', audience='', score=0):
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
    }


# ─── סורקים ספציפיים ──────────────────────────────────────────────────────────

def scrape_ganeytikva():
    """גני תקווה — גני.org.il/events/ (HTML)
    מבנה: div.content.events > div.event > .date .title .category a
    """
    city = 'גני תקווה'
    base = 'https://www.ganeytikva.org.il'
    events = []

    soup = fetch(f'{base}/events/')
    if not soup:
        return events

    # Main content wrapper for events
    events_wrap = soup.select_one('div.content.events')
    if not events_wrap:
        # fallback: search for any events-like wrapper
        events_wrap = soup.select_one('.events-wrap, .events_side_items, [class*="event"]')

    items = events_wrap.select('div.event') if events_wrap else []
    if not items:
        items = soup.select('div.event')

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

        # Date: two divs inside div.date
        date_divs = item.select('div.date div, div[class="date"] div')
        day = date_divs[0].get_text(strip=True) if date_divs else ''
        month = date_divs[1].get_text(strip=True) if len(date_divs) > 1 else ''
        date_text = f"{day} {month}".strip()

        is_child, score = is_children_event(title, '', category)
        if is_child:
            events.append(make_event(city, title, None, date_text, link or f'{base}/events/', '', category, '', score))

    return events


def scrape_kiryatono():
    """קריית אונו — JSON API
    https://www.kiryatono.muni.il/events/json/?t=<timestamp>
    """
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


def scrape_savyon():
    """סביון — JSON API
    https://savyon.muni.il/events/json/
    """
    city = 'סביון'
    base = 'https://savyon.muni.il'
    events = []

    data = fetch_json(f'{base}/events/json/')
    if not data:
        # try HTML fallback
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
    """אור יהודה — HTML
    https://www.oryehuda.muni.il/events/
    """
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


def scrape_yehud():
    """יהוד-מונוסון — JSON מוטמע ב-data-events של calendar-data div
    3000 אירועים, dept 6 = מרכז משפחה, dept 7 = גיל הרך
    """
    city = 'יהוד'
    base = 'https://yehud-monosson.muni.il'
    events = []

    # Department IDs known to be children/family related
    CHILDREN_DEPTS = {6, 7, 88, 117, 128, 132, 133, 134}
    today = date.today()

    try:
        r = requests.get(
            f'{base}/%D7%9C%D7%95%D7%97-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/',
            headers=HEADERS, timeout=22
        )
        r.encoding = 'utf-8'
        html = r.text

        from html import unescape as html_unescape
        import json as jsonlib

        m = re.search(r'class="calendar-data"\s+data-events="(\[.*?\])"', html, re.DOTALL)
        if not m:
            return events

        raw_json = html_unescape(m.group(1))
        all_events = jsonlib.loads(raw_json)

        for ev in all_events:
            title = ev.get('title', '').strip()
            if not title:
                continue
            start = ev.get('start', '')
            ev_date = parse_date(start)
            # Skip past events
            if ev_date and ev_date < today:
                continue

            url = ev.get('url', '') or f'{base}/events/'
            dept = ev.get('department_id')
            description = ev.get('description', '') or ''
            if isinstance(description, dict):
                description = str(description)
            # Skip literal placeholder values
            if description.strip().lower() in ('description', 'none', ''):
                description = ''

            # Check if children-relevant
            # dept 7 = early childhood center (all events are for kids/parents)
            # other depts: need keyword match too
            is_child, score = is_children_event(title, description[:200])
            in_core_dept = dept == 7  # always include dept 7 (early childhood)
            in_child_dept = dept in CHILDREN_DEPTS

            if not in_core_dept and not is_child:
                continue
            if in_core_dept and score == 0:
                score = 2

            events.append(make_event(city, title, ev_date, start, url, description[:200], str(dept or ''), '', score))

    except Exception as e:
        print(f"  יהוד שגיאה: {e}", file=sys.stderr)

    return events


def scrape_petahtikva():
    """פתח תקווה — האתר חסום לסריקה; מחזיר פריט הפניה"""
    city = 'פתח תקווה'
    # The PT municipality site blocks scrapers (WAF).
    # Return a single placeholder entry pointing to their events page.
    return [{
        'city': city,
        'title': '📍 לאירועי פתח תקווה — לחצי כאן לאתר העירייה',
        'date': None,
        'date_text': '',
        'url': 'https://www.petah-tikva.muni.il/events',
        'description': 'האתר של עיריית פתח תקווה חוסם סריקה אוטומטית. לחצי כאן לצפות ישירות בלוח האירועים שלהם.',
        'category': 'קישור ידני',
        'audience': '',
        'score': 0,
    }]


# ─── יצירת HTML ────────────────────────────────────────────────────────────────

def generate_html(events, city_stats):
    today = date.today()
    update_str = today.strftime('%d.%m.%Y')

    # Split: upcoming with date, no date / past
    dated_future = sorted(
        [e for e in events if e['date'] and e['date'] >= today],
        key=lambda e: (e['date'], -e['score'])
    )
    no_date = [e for e in events if not e['date']]

    def event_card(ev):
        color = CITY_COLORS.get(ev['city'], '#555')
        desc_html = ''
        if ev.get('description'):
            clean = ev['description'][:220].replace('<', '&lt;').replace('>', '&gt;')
            desc_html = f'<p class="desc">{clean}</p>'
        aud_html = ''
        if ev.get('audience'):
            aud_html = f'<span class="aud">👥 {ev["audience"]}</span>'
        cat_html = ''
        cat_val = ev.get('category', '')
        # Only show category if it's a meaningful Hebrew label (not a department ID number)
        if cat_val and not cat_val.strip().lstrip('-').isdigit() and cat_val not in (ev['city'], ev['title']):
            cat_html = f'<span class="cat">🏷 {cat_val}</span>'
        meta = ' '.join(filter(None, [aud_html, cat_html]))
        meta_html = f'<div class="meta">{meta}</div>' if meta else ''
        return (
            f'<div class="card">'
            f'<div class="city-badge" style="background:{color}">{ev["city"]}</div>'
            f'<h2 class="ev-title"><a href="{ev["url"]}" target="_blank" rel="noopener">{ev["title"]}</a></h2>'
            f'{desc_html}'
            f'{meta_html}'
            f'<a class="btn" href="{ev["url"]}" target="_blank" rel="noopener">פרטים והרשמה ←</a>'
            f'</div>'
        )

    cards_html = ''
    current_date_label = None

    for ev in dated_future:
        d_label = format_date_display(ev['date'])
        if d_label != current_date_label:
            current_date_label = d_label
            cards_html += f'<div class="date-header">{d_label}</div>\n'
        cards_html += event_card(ev) + '\n'

    if no_date:
        cards_html += '<div class="date-header undated">תאריך לא ידוע</div>\n'
        for ev in no_date:
            cards_html += event_card(ev) + '\n'

    if not cards_html:
        cards_html = '<p class="empty">לא נמצאו אירועים לילדים כרגע. נסי שוב מאוחר יותר.</p>'

    # City stats bar
    stats_html = ''
    for city, count in sorted(city_stats.items()):
        color = CITY_COLORS.get(city, '#555')
        stats_html += (
            f'<div class="stat-chip" style="border-color:{color}">'
            f'<span class="stat-dot" style="background:{color}"></span>'
            f'{city}: {count}'
            f'</div>'
        )

    return f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎈 אירועים לילדים – ערי המרכז</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  background: #eef2f7;
  color: #1a1a2e;
  direction: rtl;
}}
header {{
  background: linear-gradient(135deg, #0d1b2a 0%, #1b3a5c 60%, #2563a8 100%);
  color: #fff;
  padding: 2.2rem 1.5rem 1.8rem;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0,0,0,.35);
}}
header h1 {{ font-size: 2rem; font-weight: 800; letter-spacing: -.5px; }}
header .subtitle {{ opacity: .7; font-size: .9rem; margin-top: .3rem; }}
.stats-bar {{
  display: flex; flex-wrap: wrap; gap: .5rem;
  justify-content: center; margin-top: 1.2rem;
}}
.stat-chip {{
  display: flex; align-items: center; gap: .4rem;
  background: rgba(255,255,255,.1);
  border: 1.5px solid transparent;
  border-radius: 20px; padding: .22rem .7rem;
  font-size: .8rem; color: #fff;
}}
.stat-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
main {{ max-width: 720px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }}
.update {{
  text-align: center; color: #777; font-size: .8rem;
  margin-bottom: 1.6rem;
}}
.update a {{ color: #2563a8; text-decoration: none; font-weight: 600; }}
.date-header {{
  font-size: 1rem; font-weight: 700; color: #1b3a5c;
  margin: 2rem 0 .7rem;
  padding-right: .7rem;
  border-right: 4px solid #2563a8;
  line-height: 1.2;
}}
.date-header.undated {{ color: #999; border-color: #ccc; margin-top: 2.5rem; }}
.card {{
  background: #fff;
  border-radius: 14px;
  padding: 1.1rem 1.2rem 1rem;
  margin-bottom: .8rem;
  box-shadow: 0 2px 10px rgba(0,0,0,.07);
  transition: box-shadow .18s, transform .18s;
}}
.card:hover {{ box-shadow: 0 8px 24px rgba(0,0,0,.13); transform: translateY(-1px); }}
.city-badge {{
  display: inline-block;
  color: #fff; font-size: .7rem; font-weight: 700;
  padding: .18rem .55rem; border-radius: 20px;
  margin-bottom: .5rem; letter-spacing: .3px;
}}
.ev-title {{ font-size: 1.05rem; line-height: 1.4; margin-bottom: .4rem; }}
.ev-title a {{ color: #1a1a2e; text-decoration: none; }}
.ev-title a:hover {{ color: #1b3a5c; text-decoration: underline; }}
.desc {{
  font-size: .83rem; color: #555; line-height: 1.55;
  margin-bottom: .5rem;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}}
.meta {{ font-size: .78rem; color: #888; margin-bottom: .55rem; display: flex; gap: .8rem; flex-wrap: wrap; }}
.btn {{
  display: inline-block;
  background: #1b3a5c; color: #fff;
  padding: .32rem .85rem; border-radius: 8px;
  font-size: .8rem; font-weight: 700;
  text-decoration: none; letter-spacing: .2px;
  transition: background .18s;
}}
.btn:hover {{ background: #2563a8; }}
.empty {{ text-align: center; color: #999; margin: 4rem 0; font-size: 1.05rem; }}
@media (max-width: 500px) {{
  header h1 {{ font-size: 1.45rem; }}
  .card {{ padding: .9rem; }}
}}
</style>
</head>
<body>
<header>
  <h1>🎈 אירועים לילדים – ערי המרכז</h1>
  <p class="subtitle">גני תקווה · קריית אונו · פתח תקווה · סביון · אור יהודה · יהוד</p>
  <div class="stats-bar">{stats_html}</div>
</header>
<main>
  <p class="update">עודכן: {update_str} · {len(events)} אירועים לילדים ·
    <a href="javascript:location.reload()">רענן</a></p>
  {cards_html}
</main>
</body>
</html>'''


# ─── ריצה ראשית ───────────────────────────────────────────────────────────────

SCRAPERS = [
    ('גני תקווה',  scrape_ganeytikva),
    ('קריית אונו', scrape_kiryatono),
    ('פתח תקווה', scrape_petahtikva),
    ('סביון',      scrape_savyon),
    ('אור יהודה',  scrape_oryehuda),
    ('יהוד',       scrape_yehud),
]


def main():
    all_events = []
    city_stats = {}

    for city, fn in SCRAPERS:
        print(f'סורק {city}...', file=sys.stderr, flush=True)
        try:
            events = fn()
            city_stats[city] = len(events)
            print(f'  ✓ {len(events)} אירועים לילדים', file=sys.stderr, flush=True)
            all_events.extend(events)
        except Exception as e:
            city_stats[city] = 0
            print(f'  ✗ שגיאה: {e}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

    # מיון: קודם עתיד לפי תאריך, אז ללא תאריך
    today = date.today()
    all_events.sort(key=lambda e: (
        not (e['date'] and e['date'] >= today),
        e['date'] or date.max,
        -e['score'],
    ))

    # הסרת כפילויות: אותה עיר + אותו כותרת + אותו תאריך
    seen = set()
    unique_events = []
    for e in all_events:
        key = (e['city'], e['title'][:40].strip(), str(e['date']))
        if key not in seen:
            seen.add(key)
            unique_events.append(e)

    html = generate_html(unique_events, city_stats)
    output = Path(__file__).parent / 'אירועים_ילדים.html'
    output.write_text(html, encoding='utf-8')

    print(f'\n✅ נשמר: {output}', file=sys.stderr)
    print(f'   סה"כ {len(unique_events)} אירועים ייחודיים', file=sys.stderr)

    import subprocess
    subprocess.run(['open', str(output)])


if __name__ == '__main__':
    main()
