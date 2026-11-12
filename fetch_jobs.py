#!/usr/bin/env python3
"""UX Opportunity Radar feed: San Diego (any arrangement) + US-eligible remote."""
import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'jobs.json'
NOW = dt.datetime.now(dt.timezone.utc)
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UXOpportunityRadar/1.1)', 'Accept': 'application/json'}
TITLE = re.compile(r'\b(?:ux|ui|user experience|product design(?:er)?|interaction design(?:er)?|experience design(?:er)?|digital product design(?:er)?|design systems? design(?:er)?)\b', re.I)
EXCLUDE = re.compile(r'\b(?:manager|director|principal|staff|vp|vice president|head of|internship|intern)\b', re.I)
SAN_DIEGO = re.compile(r'\bsan[ -]diego\b', re.I)
REMOTE = re.compile(r'\b(?:remote|work from home|distributed|anywhere)\b', re.I)
US = re.compile(r'\b(?:united states|u\.?s\.?a?\.?|us[- ](?:only|based|remote)|north america)\b', re.I)
NON_US_ONLY = re.compile(r'\b(?:europe only|emea only|uk only|canada only|latam only|apac only|outside (?:the )?(?:united states|usa))\b', re.I)
YEARS = re.compile(r'\b(\d{1,2})\s*(?:\+|[-–]\s*\d{1,2})?\s*(?:years?|yrs?)(?:\s+of)?\s*(?:relevant|professional|hands-on|work|industry|prior|direct)?\s*(?:experience|in\s+(?:ux|ui|design|product|research))\b', re.I)
CUE = re.compile(r'\b(?:qualification|requirement|you have|you bring|must have|at least|minimum|preferred|experience|years|yrs|background)\b', re.I)

def plain(value):
    text = re.sub(r'(?i)</(?:p|li|div|h[1-6]|br)>|<br\s*/?>', '\n', str(value or ''))
    text = re.sub(r'<[^>]*>', ' ', text)
    return html.unescape(text).strip()

def compact(value):
    return re.sub(r'\s+', ' ', plain(value)).strip()

def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as response:
        return json.load(response)

def date_iso(value):
    if value is None or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            d = dt.datetime.fromtimestamp(value, dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat() if d <= NOW + dt.timedelta(hours=1) else None
    except (ValueError, OverflowError, TypeError):
        return None

def experience_minimum(description):
    # Preserve HTML list boundaries. Avoid company-history sentences where possible.
    chunks = re.split(r'[\n.!?]+', plain(description))
    values = []
    for chunk in chunks:
        if len(chunk) > 400 or not CUE.search(chunk):
            continue
        values.extend(int(m.group(1)) for m in YEARS.finditer(chunk) if int(m.group(1)) <= 30)
    return max(values) if values else None

def location_match(location, description, remote_flag=False):
    loc, desc = compact(location), compact(description)
    if SAN_DIEGO.search(loc):
        return 'san diego'
    if NON_US_ONLY.search(loc):
        return None
    # Remote-only is not proof of US eligibility; require explicit location evidence.
    if not (REMOTE.search(loc) or remote_flag):
        return None
    if US.search(loc) and not NON_US_ONLY.search(loc):
        return 'remote'
    # Some providers put the US restriction in the description rather than location.
    if re.search(r'\b(?:remote (?:within|in|across|from) (?:the )?(?:united states|u\.?s\.?a?\.?)|(?:united states|u\.?s\.?a?\.?)\s*[- ]based|must (?:reside|live|be based) in (?:the )?(?:united states|u\.?s\.?a?\.?))\b', desc, re.I):
        return 'remote'
    return None

def score(title, description):
    text = (title + ' ' + description).lower()
    return 50 + 20 * bool(re.search(r'fintech|financial|banking|payments', text)) + 15 * bool(re.search(r'enterprise|b2b|complex workflow', text)) + 10 * bool(re.search(r'\bai\b|artificial intelligence', text)) + 5 * bool(re.search(r'end.to.end|ownership', text))

def add(jobs, stats, source, raw_id, title, company, location, description, url, posted_at, salary='', remote_flag=False):
    stats['seen'] += 1
    title, company, description = compact(title), compact(company), compact(description)
    if not TITLE.search(title) or EXCLUDE.search(title):
        stats['rejected_title'] += 1
        return
    stats['title_matched'] += 1
    if not url or not str(url).startswith('https://'):
        stats['rejected_url'] += 1
        return
    arrangement = location_match(location, description, remote_flag)
    if not arrangement:
        stats['rejected_location'] += 1
        if len(stats['location_examples']) < 8:
            stats['location_examples'].append({'title': title, 'location': compact(location)[:100]})
        return
    stats['location_matched'] += 1
    years = experience_minimum(description)
    if years is not None and years > 5:
        stats['rejected_experience'] += 1
        return
    stats['experience_matched'] += 1
    uid = hashlib.sha256((source + ':' + str(raw_id or url)).encode()).hexdigest()[:20]
    summary = description[:185].rstrip(' ,.;') + ('…' if len(description) > 185 else '')
    jobs.append({'id': uid, 'source': source, 'title': title, 'company': company,
                 'location': compact(location) or ('U.S. remote' if arrangement == 'remote' else 'San Diego'),
                 'arrangement': arrangement, 'description': description[:2500], 'summary': summary,
                 'url': str(url), 'posted_at': date_iso(posted_at), 'min_years': years,
                 'salary': compact(salary) or None, 'salary_max': None,
                 'fit': score(title, description)})

def run():
    jobs, errors = [], []
    stats = {k: 0 for k in ('seen', 'title_matched', 'location_matched', 'experience_matched',
                           'rejected_title', 'rejected_url', 'rejected_location', 'rejected_experience')}
    stats['location_examples'] = []
    # Query the broad design category plus title searches. Dedupe across requests.
    urls = ['https://remotive.com/api/remote-jobs?category=design&limit=1000']
    for term in ('product designer', 'ux designer', 'ui ux designer'):
        urls.append('https://remotive.com/api/remote-jobs?' + urllib.parse.urlencode({'search': term, 'limit': 1000}))
    remotive_ids = set()
    for url in urls:
        try:
            data = get_json(url)
            entries = data.get('jobs', [])
            print('Remotive query:', url, 'returned', len(entries), 'records')
            for j in entries:
                ident = str(j.get('id') or j.get('url'))
                if ident in remotive_ids:
                    continue
                remotive_ids.add(ident)
                add(jobs, stats, 'Remotive', j.get('id'), j.get('title'), j.get('company_name'),
                    j.get('candidate_required_location') or 'Remote', j.get('description'),
                    j.get('url'), j.get('publication_date'), j.get('salary'))
        except Exception as e:
            errors.append('Remotive ' + url + ': ' + str(e))
    try:
        for page in range(1, 11):
            data = get_json(f'https://www.arbeitnow.com/api/job-board-api?page={page}')
            entries = data.get('data', [])
            print('Arbeitnow page', page, 'returned', len(entries), 'records')
            for j in entries:
                add(jobs, stats, 'Arbeitnow', j.get('slug'), j.get('title'), j.get('company_name'),
                    j.get('location'), j.get('description'), j.get('url'), j.get('created_at'),
                    remote_flag=j.get('remote', False))
            if not entries or not (data.get('links') or {}).get('next'):
                break
    except Exception as e:
        errors.append('Arbeitnow: ' + str(e))
    dedup = {}
    for j in jobs:
        key = (j['company'].casefold(), re.sub(r'\W+', '', j['title'].casefold()), j['url'].split('?')[0])
        dedup[key] = j
    jobs = sorted(dedup.values(), key=lambda j: (j['posted_at'] or '', j['fit']), reverse=True)
    print('Feed diagnostics:', json.dumps(stats, ensure_ascii=False))
    print(f'Published {len(jobs)} matches; errors: {errors}')
    if errors and stats['seen'] == 0:
        raise SystemExit('No source data retrieved; preserving previous feed')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'updated_at': NOW.isoformat(), 'jobs': jobs,
                               'sources': ['Remotive', 'Arbeitnow'], 'errors': errors},
                              indent=2, ensure_ascii=False) + '\n')

if __name__ == '__main__':
    run()
