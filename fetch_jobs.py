#!/usr/bin/env python3
"""UX Opportunity Radar: public job-board feeds, standard library only.

Configure company board tokens in data/sources.json. Public ATS APIs are
company-specific, not global job search engines. No applicant counts inferred.
"""
import datetime as dt
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'jobs.json'
CONFIG = ROOT / 'data' / 'sources.json'
NOW = dt.datetime.now(dt.timezone.utc)
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UXOpportunityRadar/2.0)', 'Accept': 'application/json'}
TITLE = re.compile(r'(?i)(?:\b(?:ux|ui|user experience|interaction|product|digital product|experience|design systems?)\b.{0,35}\bdesign(?:er)?\b|\bdesign(?:er)?\b.{0,35}\b(?:ux|ui|product|interaction|experience|systems?)\b|\bux\s*/\s*ui\b|\bproduct designer\b)')
EXCLUDE = re.compile(r'(?i)\b(?:manager|director|principal|staff|vp|vice president|head of|internship|intern|graphic designer|visual merchandiser)\b')
SD = re.compile(r'(?i)\bsan diego\b')
REMOTE = re.compile(r'(?i)\b(?:remote|work from home|distributed|anywhere)\b')
US = re.compile(r'(?i)\b(?:united states|u\.?s\.?a?\.?|us[- ]based|america(?:n)?|north america)\b')
CALIFORNIA = re.compile(r'(?i)\b(?:california|\bCA\b)')
FOREIGN_ONLY = re.compile(r'(?i)\b(?:europe|emea|uk only|united kingdom|canada only|canada|latam|latin america|apac|asia|australia|germany|france|india|poland|brazil|mexico|netherlands|switzerland|berlin|london)\b')
YRS = re.compile(r'(?i)(?<!\d)(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?(?:years?|yrs?)\b(?:\s+of)?(?:\s+(?:relevant|professional|hands-on|work))?\s*(?:experience|in\s+(?:ux|ui|product|design|research))?')
CUE = re.compile(r'(?i)\b(?:qualification|requirement|you have|you bring|must have|minimum|at least|experience|background|looking for|we seek|proficiency)\b')


def plain(value):
    s = html.unescape(str(value or ''))
    s = re.sub(r'(?i)<\s*(?:br|/p|/li|/div|/h\d)\b[^>]*>', '\n', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'[ \t]+', ' ', s).strip()


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=18) as resp:
        return json.load(resp)


def iso(value, unit='auto'):
    if value in (None, ''):
        return None
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if unit == 'ms' or (unit == 'auto' and stamp > 1e11): stamp /= 1000
            parsed = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
        else:
            parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=dt.timezone.utc)
        if parsed > NOW + dt.timedelta(hours=1): return None
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def min_years(description):
    """Conservative requirement parser; ambiguous clauses remain unspecified."""
    text = plain(description)
    chunks = re.split(r'\n+|(?<=[.!?])\s+', text)
    matches = []
    for chunk in chunks:
        if len(chunk) > 500 or not CUE.search(chunk): continue
        for m in YRS.finditer(chunk):
            n = int(m.group(1))
            if n <= 30: matches.append(n)
    return max(matches) if matches else None


def classify(location, description, remote_flag=False, workplace=''):
    """Conservative eligibility: San Diego any arrangement, or verified US remote."""
    loc = plain(location)
    desc = plain(description)
    if SD.search(loc): return 'san diego'
    if workplace.lower() in ('onsite', 'on-site', 'hybrid'): return None
    if not (REMOTE.search(loc) or remote_flag or workplace.lower() == 'remote'): return None
    # Foreign-only restrictions in location are decisive, even if job text mentions US.
    if FOREIGN_ONLY.search(loc) and not (US.search(loc) or CALIFORNIA.search(loc)):
        return None
    if US.search(loc) or CALIFORNIA.search(loc): return 'remote'
    # Generic 'Remote' needs affirmative US/California eligibility in job description.
    if re.fullmatch(r'(?i)(?:remote|work from home|distributed|anywhere)', loc.strip()) or not loc:
        if re.search(r'(?i)\b(?:remote\s+(?:in|within|across|from|throughout)\s+(?:the\s+)?(?:united states|u\.?s\.?a?\.?|california)|(?:united states|u\.?s\.?a?\.?|california)[ -]based\s+(?:candidates|applicants|employees)|(?:reside|live|based)\s+in\s+(?:the\s+)?(?:united states|u\.?s\.?a?\.?|california))\b', desc):
            return 'remote'
    return None


def score(title, desc):
    t = (title + ' ' + desc[:2500]).lower()
    return 50 + 20 * bool(re.search(r'fintech|financial|banking|payments', t)) + 15 * bool(re.search(r'enterprise|b2b|complex workflow', t)) + 10 * bool(re.search(r'\bai\b|artificial intelligence', t)) + 5 * bool(re.search(r'end.to.end|ownership', t))


def add(results, stats, source, raw_id, title, company, location, description, url, posted=None, salary=None, remote=False, workplace=''):
    stats['seen'] += 1
    title, company, description = plain(title), plain(company), plain(description)
    if not TITLE.search(title) or EXCLUDE.search(title):
        stats['rejected_title'] += 1; return
    stats['title_matched'] += 1
    if not str(url or '').startswith('https://'):
        stats['rejected_url'] += 1; return
    arrangement = classify(location, description, remote, workplace)
    if not arrangement:
        stats['rejected_location'] += 1
        if len(stats['location_examples']) < 12: stats['location_examples'].append({'title': title, 'location': plain(location), 'source': source})
        return
    stats['location_matched'] += 1
    years = min_years(description)
    if years is not None and years > 5:
        stats['rejected_experience'] += 1; return
    stats['experience_matched'] += 1
    uid = hashlib.sha256((source + ':' + str(raw_id or url)).encode()).hexdigest()[:20]
    summary = description[:185].rstrip(' ,.;') + ('…' if len(description) > 185 else '')
    results.append({'id': uid, 'source': source, 'title': title, 'company': company, 'location': plain(location) or ('U.S. remote' if arrangement == 'remote' else 'San Diego'), 'arrangement': arrangement, 'description': description[:2500], 'summary': summary, 'url': str(url), 'posted_at': iso(posted), 'min_years': years, 'salary': plain(salary) or None, 'salary_max': None, 'fit': score(title, description), 'applicants': None})


def fetch_remotive(results, stats):
    url = 'https://remotive.com/api/remote-jobs?category=design&limit=1000'
    data = get_json(url)
    print('Remotive:', len(data.get('jobs', [])), 'records')
    for j in data.get('jobs', []):
        add(results, stats, 'Remotive', j.get('id'), j.get('title'), j.get('company_name'), j.get('candidate_required_location') or 'Remote', j.get('description'), j.get('url'), j.get('publication_date'), j.get('salary'))


def fetch_arbeitnow(results, stats):
    for page in range(1, 9):
        data = get_json(f'https://www.arbeitnow.com/api/job-board-api?page={page}')
        items = data.get('data', [])
        print('Arbeitnow page', page, ':', len(items), 'records')
        for j in items:
            add(results, stats, 'Arbeitnow', j.get('slug'), j.get('title'), j.get('company_name'), j.get('location'), j.get('description'), j.get('url'), j.get('created_at'), remote=j.get('remote', False))
        if not items or not data.get('links', {}).get('next'): break


def fetch_greenhouse(token, company, results, stats):
    data = get_json(f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true')
    items = data.get('jobs', [])
    print('Greenhouse', token, ':', len(items), 'records')
    for j in items:
        # Greenhouse updated_at is an edit timestamp, NOT a verified posting date.
        add(results, stats, 'Greenhouse', f'{token}:{j.get("id")}', j.get('title'), company, (j.get('location') or {}).get('name'), j.get('content'), j.get('absolute_url'), posted=None)


def fetch_lever(token, company, results, stats):
    data = get_json(f'https://api.lever.co/v0/postings/{token}?mode=json')
    print('Lever', token, ':', len(data), 'records')
    for j in data:
        cats = j.get('categories') or {}
        desc = '\n'.join([plain(j.get('descriptionPlain') or j.get('description')), plain(j.get('additionalPlain') or j.get('additional')), plain(j.get('lists'))])
        location = cats.get('location') or ''
        all_locs = cats.get('allLocations') or []
        if all_locs: location += ' / ' + ' / '.join(map(str, all_locs))
        workplace = j.get('workplaceType') or ''
        add(results, stats, 'Lever', f'{token}:{j.get("id")}', j.get('text'), company, location, desc, j.get('applyUrl') or j.get('hostedUrl'), j.get('createdAt'), workplace=workplace, remote=workplace.lower() == 'remote')


def fetch_ashby(token, company, results, stats):
    data = get_json(f'https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true')
    items = data.get('jobs', [])
    print('Ashby', token, ':', len(items), 'records')
    for j in items:
        if j.get('isListed') is False: continue
        comp = j.get('compensation') or {}
        salary = comp.get('scrapeableCompensationSalarySummary') or comp.get('compensationTierSummary')
        locs = [j.get('location') or ''] + [x.get('location') or '' for x in j.get('secondaryLocations', [])]
        loc = ' / '.join(x for x in locs if x)
        add(results, stats, 'Ashby', f'{token}:{j.get("id") or j.get("jobUrl")}', j.get('title'), company, loc, j.get('descriptionPlain') or j.get('descriptionHtml'), j.get('applyUrl') or j.get('jobUrl'), j.get('publishedAt'), salary, remote=j.get('workplaceType') == 'Remote', workplace=j.get('workplaceType') or '')


def run():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    results, errors = [], []
    stats = {'seen': 0, 'title_matched': 0, 'location_matched': 0, 'experience_matched': 0, 'rejected_title': 0, 'rejected_url': 0, 'rejected_location': 0, 'rejected_experience': 0, 'location_examples': []}
    tasks = []
    if config.get('remotive', True): tasks.append(('Remotive', lambda: fetch_remotive(results, stats)))
    if config.get('arbeitnow', True): tasks.append(('Arbeitnow', lambda: fetch_arbeitnow(results, stats)))
    for provider, func in [('greenhouse', fetch_greenhouse), ('lever', fetch_lever), ('ashby', fetch_ashby)]:
        for board in config.get(provider, []):
            token = board['token']; company = board.get('company') or token
            tasks.append((f'{provider}:{token}', lambda f=func, t=token, c=company: f(t, c, results, stats)))
    for name, fn in tasks:
        try: fn()
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
            print('Source error:', errors[-1])
    unique = {}
    for job in results:
        key = (job['company'].casefold(), re.sub(r'\W+', '', job['title'].casefold()), urlparse(job['url']).path.rstrip('/').casefold())
        unique[key] = job
    jobs = sorted(unique.values(), key=lambda j: (j['posted_at'] or '', j['fit']), reverse=True)
    print('Feed diagnostics:', json.dumps(stats, ensure_ascii=False))
    print(f'Published {len(jobs)} matches; errors: {errors}')
    if errors and len(errors) == len(tasks):
        raise SystemExit('All sources failed; prior jobs.json preserved')
    # Never represent feed update time as a posting timestamp.
    payload = {'updated_at': NOW.isoformat(), 'jobs': jobs, 'sources': [name for name, _ in tasks], 'errors': errors}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    run()
