#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting Google Jobs Scraper on Render..."

# 1. Provide a dummy URL for the scraper to pick up since it uses input()
# Render runs without an interactive terminal.
echo "https://www.google.com/about/careers/applications/jobs/results/?q=%22Software%20Engineer%22&location=United%20States" | python scrape.py

# 2. Run the parser, database updater, and email notifier
python main.py

echo "Job completed successfully!"
