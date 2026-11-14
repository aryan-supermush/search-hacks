"""Check the hours of the places a plan depends on: listing vs routed web search vs recent reviews."""
import json, os, re
from datetime import datetime, timedelta, timezone
from .core import cached_post, telem_search
from .places import hours_text, parse_ranges

HOURS_WORDS = re.compile(r"clos(ed|es|ing)|hours|24 ?h|24/7|open (till|until)|opens? at|wasn.t open|not open|locked|early|\b1?\d(:\d\d)? ?(am|pm|a\.m\.|p\.m\.)", re.I)


def verify(trace, places, when, times=None):
    """places: list of place dicts; times: {key: datetime the user is near it}. Returns {key: {status, reason, evidence}}."""
    if not places:
        return {}
    names = [f"{p['name']} {p.get('address') or ''}".strip() for p in places]
    reviews = telem_search(trace, "reviews", names, {
        "providers": {"include": ["outscraper_greviews"]}, "tier": "max", "num_results": 20, "include_raw": True})
    web = telem_search(trace, "web pages", [f"{n} hours" for n in names], {
        "auto_routing": "accuracy", "tier": "extended", "num_results": 5})

    cutoff = datetime.now(timezone.utc) - timedelta(days=730)
    evidence = {p["key"]: {"reviews": [], "web": []} for p in places}
    for run in reviews.get("preprocessor_runs", []):
        if run.get("preprocessor_name") != "outscraper_greviews":
            continue
        idx = run.get("batch_index", 0)
        if idx >= len(places):
            continue
        for r in (run.get("output_payload") or {}).get("results", []):
            text, date = r.get("summary") or "", r.get("publish_date")
            if date and datetime.fromisoformat(date.replace("Z", "+00:00")) >= cutoff and HOURS_WORDS.search(text):
                evidence[places[idx]["key"]]["reviews"].append({"date": date[:10], "text": text[:400], "url": r.get("url")})
    for run in web.get("preprocessor_runs", []):
        idx = run.get("batch_index", 0)
        if idx >= len(places):
            continue
        for r in (run.get("output_payload") or {}).get("results", [])[:3]:
            evidence[places[idx]["key"]]["web"].append({"url": r.get("url"), "provider": run.get("preprocessor_name"),
                                                         "text": ((r.get("title") or "") + " " + (r.get("summary") or ""))[:500]})

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {p["key"]: {"status": "listed", "reason": "Listing only (no LLM key set to read other sources).",
                           "evidence": []} for p in places}

    # The LLM only EXTRACTS what each source states; the open/closed decision is made in code below.
    items = []
    for i, p in enumerate(places):
        ev = evidence[p["key"]]
        items.append(f"PLACE {i}: {p['name']}, {p.get('address')}\n"
                     f"WEB SNIPPETS:\n" + ("\n".join(f"- [{w['url']}] {w['text']}" for w in ev["web"]) or "- none") +
                     "\nREVIEWS THAT MENTION HOURS:\n" +
                     ("\n".join(f"- [{r['date']}] {r['text']}" for r in ev["reviews"]) or "- none"))
    prompt = (f"Extract facts about opening hours on {when:%A}s for each place. Use ONLY the text given; never guess.\n"
              "Return ONLY a JSON array, one object per place in order:\n"
              '{"place": index, "web_hours": [{"hours": "e.g. 7AM-10PM or Open 24 hours or Closed", "url": "...", '
              '"quote": "verbatim, max 120 chars"}], "closed_reports": [{"time": "e.g. 1:15 AM", "date": "YYYY-MM-DD", '
              '"quote": "verbatim, max 120 chars"}]}\n'
              f"web_hours: only snippets that state this place's hours for {when:%A} (or every day). "
              "closed_reports: only reviews where someone found the place closed at a specific clock time.\n\n"
              + "\n\n".join(items))
    data, _ = cached_post("llm", "https://api.anthropic.com/v1/messages",
                          {"model": "claude-haiku-4-5-20251001", "max_tokens": 3000,
                           "messages": [{"role": "user", "content": prompt}]},
                          {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    text = data["content"][0]["text"]
    try:
        rows = {r.get("place"): r for r in json.loads(text[text.find("["): text.rfind("]") + 1])}
    except ValueError:
        rows = {}
    out = {}
    for i, p in enumerate(places):
        out[p["key"]] = decide(p, rows.get(i) or {}, (times or {}).get(p["key"], when))
    return out


def _clock_minutes(s):
    m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", s or "", re.I)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).replace(".", "").lower()
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h * 60 + mi


def decide(place, row, at):
    """confirmed / listed / uncertain at the exact minute the user is near the place, decided in code."""
    minute = at.hour * 60 + at.minute
    agree, disagree = [], []
    for w in row.get("web_hours") or []:
        ranges = parse_ranges(str(w.get("hours", "")))
        if ranges is None:
            continue
        is_open = any(o <= minute < c or (c > 1440 and minute < c - 1440) for o, c in ranges)
        (agree if is_open else disagree).append({"url": w.get("url"), "quote": w.get("quote") or w.get("hours"), "date": None})
    for r in row.get("closed_reports") or []:
        t = _clock_minutes(r.get("time"))
        if t is not None and abs(t - minute) <= 60:
            disagree.append({"url": None, "quote": r.get("quote"), "date": r.get("date")})
    at_s = at.strftime("%-I:%M %p")
    if disagree:
        return {"status": "uncertain", "evidence": disagree[:2] + agree[:1],
                "reason": f"The listing says open at {at_s}, but {len(disagree)} other source(s) say closed then."}
    if agree:
        return {"status": "confirmed", "evidence": agree[:2],
                "reason": f"Open at {at_s} by the listing and {len(agree)} web source(s)."}
    return {"status": "listed", "evidence": [], "reason": f"Open at {at_s} by the listing; no other source found."}
