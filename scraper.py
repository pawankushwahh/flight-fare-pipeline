"""
Google Flights multi-date scraper — full field extraction
Captures: airline, times, duration, stops, layover airport,
          CO2 emissions (kg), emissions vs average (%), price, trip type.

Config at top. Run:
    pip install playwright && playwright install chromium
    mkdir -p data
    python scraper.py
"""

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import csv, time, random, re, os
from datetime import datetime, date, timedelta
from itertools import permutations

# ─── Config ──────────────────────────────────────────────────────────────────
AIRPORTS_CSV  = "india_airports.csv"
OUTPUT_CSV    = "data/flights.csv"
DAY_GAP       = 7
MONTHS_AHEAD  = 2
HEADLESS      = True
DELAY_MIN     = 3
DELAY_MAX     = 6

# ─── All output columns ───────────────────────────────────────────────────────
FIELDNAMES = [
    # Route info
    "route", "from_iata", "to_iata", "from_city", "to_city", "travel_date",
    # Flight details
    "airline", "departure", "arrival", "duration", "stops",
    "layover_airport",
    # Emissions
    "co2_kg", "co2_vs_avg",
    # Price
    "price_inr", "trip_type",
    # Meta
    "scraped_at",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────
def build_dates(gap_days, months):
    start  = date.today() + timedelta(days=1)
    end    = date.today() + timedelta(days=months * 30)
    dates, cursor = [], start
    while cursor <= end:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=gap_days)
    return dates

def load_airports(path):
    airports = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iata = row.get("IATA", "").strip()
            kind = row.get("Kind", "").strip().lower()
            if iata and kind == "large":
                airports.append({
                    "iata": iata,
                    "city": row.get("City", "").strip(),
                    "name": row.get("Name", "").strip(),
                })
    return airports

def load_done_keys(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            done.add((row.get("route", ""), row.get("travel_date", "")))
    return done

def append_flights(path, flights):
    if not flights:
        return
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if is_new:
            w.writeheader()
        w.writerows(flights)

def build_url(from_code, to_code, travel_date):
    return (
        f"https://www.google.com/travel/flights/search"
        f"?hl=en&gl=IN&curr=INR"
        f"&q=Flights+from+{from_code}+to+{to_code}+on+{travel_date}"
    )

# ─── Card parser — extracts every visible field ───────────────────────────────
def parse_card(card, route, travel_date):
    try:
        text = card.inner_text()
        if not text.strip():
            return None

        # ── Price ─────────────────────────────────────────────────────────────
        price_match = re.search(r"₹([\d,]+)", text)
        if not price_match:
            return None
        price = price_match.group(1).replace(",", "")

        # ── Trip type (round trip / one way) ──────────────────────────────────
        trip_type = ""
        if re.search(r"round\s*trip", text, re.I):
            trip_type = "Round trip"
        elif re.search(r"one\s*way", text, re.I):
            trip_type = "One way"

        # ── Times ─────────────────────────────────────────────────────────────
        times = re.findall(r"\d{1,2}:\d{2}\s?[AP]M", text)
        departure = times[0] if len(times) > 0 else ""
        arrival   = times[1] if len(times) > 1 else ""

        # ── Duration ──────────────────────────────────────────────────────────
        dur = re.search(r"\d+\s*hr\s*(?:\d+\s*min)?", text, re.I)
        duration = dur.group(0).strip() if dur else ""

        # ── Stops + layover airport ───────────────────────────────────────────
        # "1 stop" or "Nonstop" or "2 stops"
        stop_match = re.search(r"(Nonstop|\d+\s*stop[s]?)", text, re.I)
        stops = stop_match.group(0).strip() if stop_match else ""

        # Layover airport code: appears as "XXX–YYY" route code inside card
        # e.g. "BHO–LKO" → layover is LKO when origin is BHO
        layover_airport = ""
        layover_codes = re.findall(r"\b([A-Z]{3})–([A-Z]{3})\b", text)
        if layover_codes:
            # The last segment's destination before final airport = layover
            # For multi-stop: BHO–DEL DEL–LKO → layover = DEL
            if len(layover_codes) > 1:
                layover_airport = layover_codes[0][1]   # intermediate stop
            elif stops and stops != "Nonstop":
                layover_airport = layover_codes[0][1]   # only segment shown

        # ── CO2 emissions ─────────────────────────────────────────────────────
        # "117 kg CO2e"
        co2_match = re.search(r"(\d+)\s*kg\s*CO2", text, re.I)
        co2_kg = co2_match.group(1) if co2_match else ""

        # Emissions vs average: "+13% emissions" or "-10% emissions" or "Avg emissions"
        co2_vs = ""
        avg_match = re.search(
            r"([+\-−]?\s*\d+\s*%)\s*emissions|Avg\s*emissions", text, re.I
        )
        if avg_match:
            if avg_match.group(1):
                co2_vs = avg_match.group(1).replace(" ", "").replace("−", "-")
            else:
                co2_vs = "Avg"

        # ── Airline ───────────────────────────────────────────────────────────
        # Appears before departure time in the card text
        pre_time = text.split(times[0])[0] if times else text
        airline_lines = [
            ln.strip() for ln in pre_time.splitlines()
            if ln.strip()
            and "₹" not in ln
            and not re.match(r"^\d", ln)
            and not re.search(r"CO2|emission|kg", ln, re.I)
            and len(ln.strip()) < 60
        ]
        airline = airline_lines[-1] if airline_lines else ""

        return {
            "route":           route["code"],
            "from_iata":       route["from"],
            "to_iata":         route["to"],
            "from_city":       route["from_city"],
            "to_city":         route["to_city"],
            "travel_date":     travel_date,
            "airline":         airline,
            "departure":       departure,
            "arrival":         arrival,
            "duration":        duration,
            "stops":           stops,
            "layover_airport": layover_airport,
            "co2_kg":          co2_kg,
            "co2_vs_avg":      co2_vs,
            "price_inr":       price,
            "trip_type":       trip_type,
            "scraped_at":      datetime.now().isoformat(),
        }
    except Exception as e:
        return None

# ─── Scrape one route × one date ──────────────────────────────────────────────
def scrape_one(page, route, travel_date):
    url = build_url(route["from"], route["to"], travel_date)
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"    ✗ goto: {e}")
        return []

    page.wait_for_timeout(2000)

    for sel in ["button[aria-label='Close']", "button[jsname='VnjF5e']"]:
        try:
            page.locator(sel).first.click(timeout=800)
        except Exception:
            pass

    if "explore" in page.url:
        print(f"    ⚠  Redirected to Explore")
        return []

    loaded_sel = None
    for sel in ["li.pIav2d", "ul.Rk10dc > li", "[jsname='IWWDBc']"]:
        try:
            page.wait_for_selector(sel, timeout=15000)
            loaded_sel = sel
            break
        except PWTimeout:
            continue

    if not loaded_sel:
        print(f"    ⚠  No results")
        return []

    page.wait_for_timeout(1200)
    cards = page.locator(loaded_sel).all()
    return [f for c in cards if (f := parse_card(c, route, travel_date))]

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(AIRPORTS_CSV):
        print(f"✗  '{AIRPORTS_CSV}' not found.")
        return

    airports = load_airports(AIRPORTS_CSV)
    print(f"✅  {len(airports)} large airports: {[a['iata'] for a in airports]}")

    routes = [
        {
            "from": a["iata"], "to": b["iata"],
            "from_city": a["city"], "to_city": b["city"],
            "code": f"{a['iata']}-{b['iata']}",
        }
        for a, b in permutations(airports, 2)
    ]
    dates = build_dates(DAY_GAP, MONTHS_AHEAD)

    total = len(routes) * len(dates)
    print(f"✅  {len(routes)} routes × {len(dates)} dates = {total} pages")
    print(f"⏱   ~{total * 20 // 60} min estimated\n")

    done     = load_done_keys(OUTPUT_CSV)
    todo     = [(r, d) for r in routes for d in dates if (r["code"], d) not in done]
    print(f"♻️   {len(done)} already done → {len(todo)} remaining\n")

    print(f"{'Route':<12} {'Date':<12} {'Flights':>7}  {'Fields captured'}")
    print("─" * 65)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        for i, (route, travel_date) in enumerate(todo, 1):
            remaining_sec = (len(todo) - i) * ((DELAY_MIN + DELAY_MAX) / 2 + 15)
            eta = f"{int(remaining_sec // 3600)}h {int((remaining_sec % 3600) // 60)}m"

            flights = scrape_one(page, route, travel_date)
            append_flights(OUTPUT_CSV, flights)

            # Show which fields were populated on first flight
            sample_fields = ""
            if flights:
                f = flights[0]
                parts = []
                if f.get("airline"):      parts.append("airline")
                if f.get("co2_kg"):       parts.append(f"CO2:{f['co2_kg']}kg")
                if f.get("co2_vs_avg"):   parts.append(f"vs_avg:{f['co2_vs_avg']}")
                if f.get("layover_airport"): parts.append(f"via:{f['layover_airport']}")
                if f.get("trip_type"):    parts.append(f.get("trip_type",""))
                sample_fields = ", ".join(parts)

            print(
                f"[{i:>4}/{len(todo)}] {route['code']:<12} {travel_date}  "
                f"{len(flights):>3} flights   {sample_fields}   ETA {eta}"
            )

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        browser.close()

    total_rows = sum(1 for _ in open(OUTPUT_CSV)) - 1
    print(f"\n✅  Done! {total_rows} total rows saved → {OUTPUT_CSV}")
    print(f"\nColumns in output:")
    for col in FIELDNAMES:
        print(f"   • {col}")

if __name__ == "__main__":
    main()