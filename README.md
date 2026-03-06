# Careers Job Scraper and Notifier

This project is an automated Python scraper designed to continuously monitor the Careers portal for new job postings (specifically "Software Engineer" roles in the United States). It fetches the latest job listings, saves them to a local SQLite database to track what has already been seen, and sends an email notification containing any new job opportunities.

## How it Works

The project is split into two main scripts:

1. **`scrape.py`**: Uses Selenium WebDriver (in headless mode) to automate a Google Chrome browser. It navigates through multiple pages of Google Careers search results, extracts the raw HTML of each job card, and saves them locally into a `data/` directory.
2. **`main.py`**: Uses BeautifulSoup4 to parse the saved HTML files and extract key information: Job Title, Location, Minimum Qualifications, and the Application Link. It then checks these jobs against a local SQLite database (`data.db`). If a job is new, it adds it to the database, logs it to a `new_jobs.csv` file, and sends an email alert using Gmail's SMTP server.

## Prerequisites

Before you can run this project, you need to have the following installed:

* **Python 3.10+**
* **Google Chrome** (Required for Selenium)

## Installation

1. **Clone or Download the Repository**
2. **Set up a Virtual Environment (Recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
3. **Install Dependencies:**
   Install the required Python packages using the provided `requirements.txt` file:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment Variables:**
   Create a `.env` file in the root directory of the project. You must configure your email credentials for the notification system to work. 
   
   *Important: You must use an "App Password" if you are using a Gmail account with 2-Step Verification enabled. Do not use your primary Google account password.*

   Add the following variables to your `.env` file:
   ```env
   EMAIL_ADDRESS="your_sender_email@gmail.com"
   EMAIL_PASSWORD="your_gmail_app_password"
   RECEIVER_EMAIL="your_receiving_email@example.com"
   ```

## Usage

To run the full scraping and notification process, you need to execute both scripts in sequence.

1. **Run the Web Scraper:**
   First, run `scrape.py` to fetch the latest job data from Google Careers and save the HTML files locally.
   ```bash
   python scrape.py
   ```
   *Note: This script takes some time to run as it parses through ~30 pages, pausing between each to avoid rate limits.*

2. **Run the Parser and Notifier:**
   Once `scrape.py` finishes, run `main.py` to parse the downloaded HTML, update the database, and trigger the email notification.
   ```bash
   python main.py
   ```

## Output

* **`data/` Directory**: Contains the raw HTML snippets of the scraped jobs.
* **`data.db` (SQLite Database)**: Keeps a persistent record of all scraped jobs to prevent duplicate notifications.
* **`new_jobs.csv`**: A CSV file generated only when new jobs are found during the current run.
* **Email Notification**: An email containing the details (Title, Location, Qualifications, Link) of any newly discovered jobs.

## Deployment Note

If you plan to deploy this project to a cloud scheduling service (like Render Cron Jobs or AWS Lambda), be aware that the local SQLite database (`data.db`) will be lost between runs in ephemeral environments, resulting in duplicate emails. For cloud deployment, you should modify `main.py` to connect to a persistent remote database (like PostgreSQL via Supabase or Neon).
