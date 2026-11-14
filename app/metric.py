"""Minutes without an open door: walking/waiting time with no open place within RADIUS metres."""
from .core import haversine
from .places import open_at

RADIUS = 100


def anchors_for(itin, origin, destination, city_origin, city_dest):
    """Plain-text locations to search places around: origin, every stop, destination."""
    out = [origin]
    for s in itin["segments"]:
        if s["kind"] == "ride":
            suffix = " station" if s.get("vehicle") in ("HEAVY_RAIL", "COMMUTER_TRAIN", "RAIL") else ""
            for stop in (s["from"], s["to"]):
                city = city_dest if stop and stop.lower().startswith(city_dest.lower().split(",")[0].lower()) else city_origin
                out.append(f"{stop}{suffix}, {city}")
    out.append(destination)
    seen, uniq = set(), []
    for a in out:
        if a.lower() not in seen:
            seen.add(a.lower())
            uniq.append(a)
    return uniq


def evaluate(points, places, status=None):
    """Return uncovered minutes, and for each point the open places covering it.

    status: {place_key: 'confirmed'|'listed'|'uncertain'}; uncertain places do not count."""
    status = status or {}
    uncovered, covered_by = 0.0, []
    for p in points:
        cover = []
        for pl in places:
            if status.get(pl["key"]) == "uncertain":
                continue
            d = haversine(p["lat"], p["lng"], pl["lat"], pl["lng"])
            if d <= RADIUS and open_at(pl, p["t"]) is True:
                cover.append((round(d), pl["key"]))
        cover.sort()
        covered_by.append(cover)
        if not cover:
            uncovered += p["secs"]
    return round(uncovered / 60, 1), covered_by


def anchor_places(points, covered_by, min_minutes=2.0):
    """Places that are the ONLY open door for at least min_minutes: these decide the number, so we verify them."""
    sole = {}
    for p, cover in zip(points, covered_by):
        if len(cover) == 1:
            sole[cover[0][1]] = sole.get(cover[0][1], 0) + p["secs"] / 60
    return [k for k, m in sorted(sole.items(), key=lambda x: -x[1]) if m >= min_minutes]
