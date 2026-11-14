"""Place discovery through Telem's Google Maps providers, and opening-hours parsing."""
import re
from datetime import datetime, timedelta
from .core import telem_search

CATEGORIES = ["convenience store", "restaurant", "cafe", "gas station", "pharmacy", "grocery store"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def find_places(trace, anchors, categories=CATEGORIES):
    """anchors: list of plain-text locations ('Maude & Mary, Sunnyvale, CA').

    Telem caps one call at 160 results (queries x num_results), so 16 queries of 10 per call."""
    queries = [f"{c} near {a}" for a in anchors for c in categories]
    places = {}
    for i in range(0, len(queries), 16):
        data = telem_search(trace, "map listings", queries[i:i + 16], {
            "providers": {"include": ["outscraper_gmaps"]}, "tier": "max", "num_results": 10, "include_raw": True})
        for run in data.get("preprocessor_runs", []):
            for r in (run.get("output_payload") or {}).get("results", []):
                p = _normalize(r, run.get("preprocessor_name"))
                if p and p["key"] not in places:
                    places[p["key"]] = p
    return list(places.values()), len(queries)


def _normalize(r, provider):
    e = r.get("enrichments") or {}
    lat, lng = e.get("lat"), e.get("lng")
    if lat is None and isinstance(e.get("coordinates"), dict):
        lat, lng = e["coordinates"].get("latitude"), e["coordinates"].get("longitude")
    hours = e.get("hours")
    if not hours and isinstance(e.get("openingHours"), list):
        hours = {h.get("day"): h.get("hours") for h in e["openingHours"]}
    if lat is None or not hours:
        return None
    if (e.get("business_status") or e.get("businessStatus") or "OPERATIONAL").upper() not in ("OPERATIONAL", ""):
        return None
    return {"key": e.get("place_id") or e.get("placeId") or r["url"], "name": r.get("title"), "lat": lat, "lng": lng,
            "address": e.get("address"), "category": e.get("category") or e.get("type"), "hours": hours,
            "url": r.get("url"), "rating": e.get("rating"), "provider": provider}


_TIME = r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?"


def _to_min(h, m, ap, fallback_ap=None):
    h, m = int(h), int(m or 0)
    ap = (ap or fallback_ap or "").replace(".", "").lower()
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h * 60 + m


def parse_ranges(text):
    """'7AM-12AM' / '7a.m.-9p.m.' / '5-8:30p.m.' / 'Open 24 hours' / 'Closed' -> [(open_min, close_min)] or None."""
    t = text.replace("–", "-").replace(" ", " ").replace(" ", " ").strip()
    low = t.lower()
    if "24 hours" in low:
        return [(0, 24 * 60)]
    if low.startswith("closed"):
        return []
    m = re.match(_TIME + r"\s*-\s*" + _TIME, t, re.I)
    if not m:
        return None
    h1, m1, ap1, h2, m2, ap2 = m.groups()
    close = _to_min(h2, m2, ap2)
    # '5-8:30p.m.' -> start inherits pm unless that would put it after the close
    open_ = _to_min(h1, m1, ap1, ap2)
    if ap1 is None and open_ > close:
        open_ = _to_min(h1, m1, None, "am")
    if close <= open_:
        close += 24 * 60  # past midnight
    return [(open_, close)]


def open_at(place, when: datetime):
    """True / False, or None when hours can't be read."""
    def ranges(day):
        vals = place["hours"].get(day)
        if vals is None:
            return None
        out = []
        for v in (vals if isinstance(vals, list) else [vals]):
            r = parse_ranges(str(v))
            if r is None:
                return None
            out.extend(r)
        return out

    minute = when.hour * 60 + when.minute
    today = ranges(DAYS[when.weekday()])
    yesterday = ranges(DAYS[(when.weekday() - 1) % 7])
    if today is None:
        return None
    if any(o <= minute < c for o, c in today):
        return True
    if yesterday and any(c > 24 * 60 and minute < c - 24 * 60 for o, c in yesterday):
        return True
    return False


def hours_text(place, when):
    v = place["hours"].get(DAYS[when.weekday()])
    return ", ".join(v) if isinstance(v, list) else str(v)
