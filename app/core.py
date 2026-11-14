"""Shared helpers: config, disk cache, HTTP with retries, geometry, Telem trace."""
import hashlib, json, math, os, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))


load_env()
TELEM_BASE = os.environ.get("TELEM_BASE_URL", "https://hack.telem.ai/api/router") + "/v1"


def cached_post(kind, url, body, headers, timeout=120):
    """POST with a disk cache keyed by url+body, retrying only 429/503/504."""
    key = hashlib.sha256((url + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:24]
    f = CACHE / f"{kind}-{key}.json"
    if f.exists():
        return json.loads(f.read_text()), True
    for attempt in range(4):
        r = httpx.post(url, json=body, headers=headers, timeout=timeout)
        if r.status_code in (429, 503, 504) and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        break
    if r.status_code >= 400:
        raise RuntimeError(f"{kind} HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    f.write_text(json.dumps(data))
    return data, False


def cached_get(kind, url, timeout=30):
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    f = CACHE / f"{kind}-{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = httpx.get(url, timeout=timeout)
    r.raise_for_status()
    f.write_text(r.text)
    return r.json()


class Trace:
    """Counts Telem calls by kind and records which providers were used."""

    def __init__(self):
        self.calls = {}
        self.providers = set()
        self.routing = []
        self.lines = []

    def telem(self, kind, response):
        self.calls[kind] = self.calls.get(kind, 0) + 1
        for run in response.get("preprocessor_runs", []):
            if run.get("status") == "succeeded":
                self.providers.add(run.get("preprocessor_name"))
        for r in response.get("routing") or []:
            self.routing.append(r.get("providers"))

    def log(self, line):
        self.lines.append(line)


def telem_search(trace, kind, queries, search):
    body = {"user_input": [{"query": q} for q in queries], "search": search}
    data, _ = cached_post("telem", TELEM_BASE + "/search", body,
                          {"Authorization": f"Bearer {os.environ['TELEM_API_KEY']}"})
    trace.telem(kind, data)
    return data


def haversine(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def decode_polyline(s):
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lng += delta
        pts.append((lat / 1e5, lng / 1e5))
    return pts
