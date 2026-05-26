#!/bin/bash
# Commit and push the latest scraped data
# Usage: bash push_data.sh

set -e

if [ ! -f "data/flights.csv" ]; then
  echo "✗  data/flights.csv not found — nothing to push"
  exit 1
fi

ROWS=$(wc -l < data/flights.csv)
DATE=$(date +'%Y-%m-%d %H:%M')

git add data/flights.csv
git commit -m "data: scrape ${DATE} — ${ROWS} rows total"
git push

echo "✅  Pushed — ${ROWS} rows in data/flights.csv"