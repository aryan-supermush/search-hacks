# Stride

**Know your route. Take it in stride.**

Stride compares Google's fastest public-transport route with the routes that keep you near open businesses. For every option it counts the minutes you would spend walking or waiting with **nothing open nearby**: no open shop, café, restaurant, gas station or pharmacy within 100 m (about a 1-minute walk). Opening hours are checked across several sources, and places with doubtful hours are not counted.

Built at SearchHack (Telem AI), Sunnyvale, 14 Nov 2026.

## How it works

1. **Routes.** Google Routes API is queried for every public-transport option: the default answer, plus bus-only, train, light-rail and rail searches, plus later departures. That gives 12–16 options per trip instead of Google's 6.
2. **Places.** Telem searches Google Maps listings (`outscraper_gmaps`) around every stop, batched (Telem allows 160 results per call).
3. **Minute by minute.** Each walking and waiting minute is checked: is any business open within 100 m at that exact time?
4. **Hours check.** For the places a route depends on, Telem fetches Google Reviews (`outscraper_greviews`) and runs an auto-routed web search. Claude Haiku only extracts the hours each source states; whether a place is open at that minute is decided in code.
5. **Ranking.** Google's fastest route on the left; Stride's two options with the fewest minutes with nothing open nearby on the right, even if the trip takes longer.
6. **Conditions.** Daylight, temperature, rain chance and AQI from Open-Meteo.

Stride reports facts (open, closed, hours checked or doubtful). It is not a safety rating and uses no crime or crowd data.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000.

## Keys (in `.env`, never in git)

| Variable | What for |
|---|---|
| `TELEM_API_KEY` | Telem search (places, reviews, web) |
| `TELEM_BASE_URL` | Optional. Defaults to the hackathon router `https://hack.telem.ai/api/router` |
| `GOOGLE_MAPS_API_KEY` | Google Routes API (transit) |
| `ANTHROPIC_API_KEY` | Claude Haiku, extracts stated opening hours |

## Code

| File | Does |
|---|---|
| `app/routes.py` | Google Routes → timed walk / wait / ride segments, sample points |
| `app/places.py` | Telem place search, opening-hours parser |
| `app/metric.py` | Minutes with nothing open nearby |
| `app/verify.py` | Hours check across listing, web and reviews |
| `app/plan.py` | Gathers options, ranks them, builds the response |
| `app/conditions.py` | Open-Meteo weather, daylight, AQI |
| `app/main.py` | FastAPI: `POST /api/plan`, serves the page |
| `static/index.html` | The app (Leaflet map, Esri Light Gray basemap) |

Every external response is cached on disk in `cache/` (not committed).

## Demo trips

From `880 W Maude Ave, Sunnyvale, CA 94085`:

| Ready to leave | To | What it shows |
|---|---|---|
| Sat 14 Nov, 7:00 PM | Santa Clara University, Santa Clara, CA | Google: 25 min trip, 12 min with nothing open. Stride: Bus 21, 41 min trip, 3 min. Starbucks not counted (listed till 9 PM, 2 sources say 7:30 PM) |
| Sun 15 Nov, 6:00 AM | Palo Alto Caltrain Station, Palo Alto, CA | Google: 42 min, 25 min with nothing open. Stride: Rapid 523 → 522, 56 min, 9 min |
| Sat 14 Nov, 7:00 PM | San Jose Diridon Station, San Jose, CA | Google's fastest is also the best; Stride says so |

## Notes

- Hackathon demo using Telem's providers. Platform terms would need review before a real launch.
- First run of a new trip takes 30–90 s; cached trips load instantly. Avoid running several new trips at once (Telem rate limit).
