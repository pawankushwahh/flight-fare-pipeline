# ✈️ India Flight Fare Scraper

Scrapes flight fares from Google Flights for all major Indian airport pairs across future dates. Stores results as CSV in `data/`.

---

## Repo structure

```
flight-scraper/
├── scraper.py            # main scraper (Playwright)
├── india_airports.csv    # source airport list (large airports only)
├── requirements.txt      # Python dependencies
├── .gitignore
├── README.md
└── data/
    ├── flights.csv       # scraped output — committed to git
    └── error_*.png       # debug screenshots — gitignored
```

---

## Setup

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/flight-scraper.git
cd flight-scraper

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Create data folder
mkdir -p data
```

---

## Run

```bash
python scraper.py
```

The scraper will print a summary on start:
```
✅  11 large airports loaded
✅  110 routes (both directions)
✅  9 date points (every 7 days, 2 months)
📊  Total pages: 990  |  ETA: ~5.5 hr
♻️   47 already done → 943 remaining (now all 990 completed -> 0 remaining )
```

It is **resumable** — if interrupted, restart and it picks up where it left off (skips rows already in `data/flights.csv`).

---

## Output columns

| Column | Example | Description |
|---|---|---|
| `route` | `BOM-DEL` | Origin–destination IATA pair |
| `from_iata` | `BOM` | Origin airport code |
| `to_iata` | `DEL` | Destination airport code |
| `from_city` | `Mumbai` | Origin city |
| `to_city` | `Delhi` | Destination city |
| `travel_date` | `2026-06-02` | Date of travel |
| `airline` | `Air India` | Airline name |
| `departure` | `7:50 PM` | Departure time |
| `arrival` | `9:25 AM` | Arrival time |
| `duration` | `2 hr 15 min` | Total flight duration |
| `stops` | `1 stop` / `Nonstop` | Number of stops |
| `layover_airport` | `DEL` | Layover airport IATA (if any) |
| `co2_kg` | `117` | CO2 emissions in kg |
| `co2_vs_avg` | `+13%` / `Avg` / `-10%` | Emissions vs route average |
| `price_inr` | `11289` | Price in INR |
| `trip_type` | `Round trip` | Round trip or One way |
| `scraped_at` | `2026-05-26T01:21:19` | Timestamp of scrape |

---

## Config (top of scraper.py)

```python
AIRPORTS_CSV  = "india_airports.csv"
OUTPUT_CSV    = "data/flights.csv"
DAY_GAP       = 7        # days between scraped dates
MONTHS_AHEAD  = 2        # how far ahead to scrape
HEADLESS      = True     # False = show browser (debug)
DELAY_MIN     = 3        # min seconds between pages
DELAY_MAX     = 6        # max seconds between pages
```

---

## Committing scraped data

After each run, commit the updated CSV:

```bash
git add data/flights.csv
git commit -m "data: scrape $(date +'%Y-%m-%d') — $(wc -l < data/flights.csv) rows"
git push
```

Or use the helper script:

```bash
bash push_data.sh
```

---

## Notes

- Google Flights sometimes redirects Indian-locale users to the Explore map page. The scraper detects and skips this automatically.
- Debug screenshots for failed routes are saved to `data/error_ROUTE.png` (gitignored).
- Large airports only — small/medium airports often have no scheduled commercial service.
- Scraping Google Flights is against their ToS. Use this for personal research only.