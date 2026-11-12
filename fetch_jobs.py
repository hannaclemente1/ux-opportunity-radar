    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def date_iso(value):
    if value is None or value == "": return None
    try:
        if isinstance(value, (int, float)):
            d = dt.datetime.fromtimestamp(value, dt.timezone.utc)
        else:
            v = str(value).strip().replace("Z", "+00:00")
            d = dt.datetime.fromisoformat(v)
            if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        if d > NOW + dt.timedelta(hours=1): return None
        return d.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, OverflowError, TypeError):
        return None

def min_experience(description):
    # Avoid claiming a requirement when it cannot be confidently determined.
    text = plain(description)
    chunks = re.split(r"(?<=[.!?])\s+|[\n•]", text)
    found = []
    for chunk in chunks:
        if not REQUIREMENT_CUE.search(chunk) or len(chunk) > 450: continue
        for m in EXPERIENCE.finditer(chunk):
            n = int(m.group(1) or m.group(3))
            if n <= 30: found.append(n)
    # Multiple requirements may refer to different skill sets; take the highest stated minimum.
    return max(found) if found else None

def location_match(location, description, remote_flag=False):
    """Return UI-compatible location category or None.

    San Diego jobs may be on-site, hybrid or remote.
    Jobs outside San Diego must explicitly permit U.S. remote work.
    """
    loc = plain(location)
    desc = plain(description)
    if SD.search(loc):
        return "san diego"

    # Do not treat a generic 'remote' flag as proof of U.S. eligibility.
    # Some feeds advertise remote jobs limited to another country.
    if NOT_US.search(loc):
        return None
    if not (US_REMOTE.search(loc) or remote_flag):
        return None

    # Explicitly U.S.-wide remote or U.S.-based remote applicants.
    if US.search(loc):
        return "remote"
    # Some feeds use 'Remote' for location and specify eligibility in the ad.
    if re.fullmatch(r"(?:remote|work from home|distributed)", loc, re.I) and re.search(
        r"\b(?:remote (?:within|in|across|from) (?:the )?(?:united states|u\.?s\.?|usa)|"
        r"(?:united states|u\.?s\.?|usa)[ -]based (?:applicants|candidates|employees)|"
        r"must (?:reside|live|be based) in (?:the )?(?:united states|u\.?s\.?|usa))\b",
        desc, re.I
    ):
        return "remote"
    return None

def score(title, description):
    text = (title+" "+description).lower()
    return 50 + (20 if re.search(r"fintech|financial|banking|payments",text) else 0) + (15 if re.search(r"enterprise|b2b|complex workflow",text) else 0) + (10 if re.search(r"\bai\b|artificial intelligence",text) else 0) + (5 if re.search(r"end.to.end|ownership",text) else 0)

def add(out, source, raw_id, title, company, location, description, url, posted_at, salary="", remote_flag=False, stats=None):
    title, company, description = plain(title), plain(company), plain(description)
    if stats is not None: stats["seen"] += 1
    if not ROLE.search(title) or not DESIGNER.search(title) or EXCLUDE.search(title): return
    if stats is not None: stats["title_matched"] += 1
    if not url or not str(url).startswith("https://"): return
    arrangement = location_match(location, description, remote_flag)
    if not arrangement: return
    if stats is not None: stats["location_matched"] += 1
    years = min_experience(description)
    if years is not None and years > 5: return
    if stats is not None: stats["experience_matched"] += 1
    uid = hashlib.sha256((source+":"+str(raw_id or url)).encode()).hexdigest()[:20]
    summary = description[:185].rstrip(" ,.;") + ("…" if len(description)>185 else "")
    out.append(dict(id=uid, source=source, title=title, company=company, location=plain(location) or ("U.S. remote" if arrangement=="remote" else "San Diego"), arrangement=arrangement, description=description[:2500], summary=summary, url=str(url), posted_at=date_iso(posted_at), min_years=years, salary=plain(salary) or None, salary_max=None, fit=score(title,description)))

def run():
    jobs, errors = [], []
    stats = {"seen": 0, "title_matched": 0, "location_matched": 0, "experience_matched": 0}
    try:
        data=get_json("https://remotive.com/api/remote-jobs?category=design&limit=1000")
        for j in data.get("jobs", []):
            add(jobs,"Remotive",j.get("id"),j.get("title"),j.get("company_name"),j.get("candidate_required_location") or "Remote",j.get("description"),j.get("url"),j.get("publication_date"),j.get("salary"),stats=stats)
    except Exception as e: errors.append("Remotive: "+str(e))
    # Arbeitnow pages are often capped; scan up to 5 pages.
    try:
        for page in range(1,6):
            data=get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
            items=data.get("data", [])
            for j in items:
                add(jobs,"Arbeitnow",j.get("slug"),j.get("title"),j.get("company_name"),j.get("location"),j.get("description"),j.get("url"),j.get("created_at"),"",j.get("remote",False),stats=stats)
            if not data.get("links",{}).get("next") or not items: break
    except Exception as e: errors.append("Arbeitnow: "+str(e))
    previous = {}
    if OUT.exists():
        try: previous={j["id"]:j for j in json.loads(OUT.read_text()).get("jobs",[])}
        except (ValueError,KeyError): pass
    # Keep previously discovered listings for 45 days, but do not claim still-open status.
    # Avoid retaining stale listings: only current source results are published.
    dedup={}
    for j in jobs:
        key=(j["company"].casefold(),re.sub(r"\W+","",j["title"].casefold()),j["url"].split("?")[0])
        dedup[key]=j
    jobs=list(dedup.values())
    jobs.sort(key=lambda j:(j["posted_at"] or "",j["fit"]),reverse=True)
    if errors and not jobs:
        print("All sources failed; preserving prior feed:", errors)
        raise SystemExit(1)
    OUT.write_text(json.dumps(dict(updated_at=NOW.isoformat(),jobs=jobs,sources=["Remotive","Arbeitnow"],errors=errors),indent=2,ensure_ascii=False)+"\n")
    print(f"Feed diagnostics: {stats}")
    print(f"Published {len(jobs)} matches; errors: {errors}")

if __name__=="__main__": run()
