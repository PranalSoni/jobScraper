# 🚀 AI-Powered Job Scraper & Notifier

An intelligent, fully automated web scraper that leverages Selenium and Google's Gemini LLM to extract job postings from any careers page or ATS (Applicant Tracking System), store them in a database, and notify you via email when new jobs become available.

## ✨ Features

- **🤖 AI-Powered Parsing**: Uses Google Gemini to understand complex, unstandardized HTML from various company job boards and normalize it into a structured format.
- **🧭 Smart Pagination**: The LLM automatically determines how to navigate to the next page of job listings (evaluating "Next" buttons, pagination URLs, etc.).
- **🗄️ Database Storage**: Saves job postings to a local SQLite database (`data.db`) ensuring no duplicate jobs are processed twice. 
- **📧 Email Notifications**: Get a clean, formatted email alert summarizing any new job postings discovered in the latest run.
- **🐳 Dockerized**: Fully containerized with Headless Chromium and Selenium configured out-of-the-box. Ready to easily deploy!
- **📄 CSV Exports**: Automatically logs newly found jobs for each run into a `new_jobs.csv` file.

## 🛠️ Technology Stack

- **Python 3.11**
- **Selenium** (for rendering JavaScript-heavy pages)
- **LangChain & Google GenAI** (for intelligent HTML parsing and pagination logic)
- **BeautifulSoup4** (for HTML cleaning and data extraction)
- **SQLite3 & Pandas** (for data persistence and CSV exports)
- **Docker** (for robust deployment)

## ⚙️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/PranalSoni/jobScraper.git
cd jobScraper
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and add the following required credentials:

```env
# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key

# Scraper Settings
TARGET_URL=https://careers.company.com/jobs
MAX_PAGES=10  # Optional (default is 10)

# Email Notification Settings
EMAIL_ADDRESS=your_sender_email@gmail.com
EMAIL_PASSWORD=your_app_password
RECEIVER_EMAIL=your_receiver_email@example.com
```
*Note: For Gmail, you will need to generate an [App Password](https://myaccount.google.com/apppasswords) for the `EMAIL_PASSWORD`.*

### 3. Run Locally (Without Docker)

Install dependencies and run the script:
```bash
pip install -r requirements.txt
python main2.py
```
*Make sure you have Chrome/Chromium installed on your local machine if you are running outside of Docker.*

### 4. Run with Docker 🐳 (Recommended)

The easiest way to run the scraper without worrying about web drivers or system dependencies is using Docker:

```bash
docker build -t ai-job-scraper .
docker run --env-file .env -v $(pwd)/data:/app/data ai-job-scraper
```
*(The `-v $(pwd)/data:/app/data` flag ensures your SQLite database and raw/normalized HTML logs persist locally across container runs).*

## 📁 Project Structure

```
├── data/               # Persistent directory for DB, CSV, and HTML logs
│   ├── data.db         # SQLite database storing all seen jobs
│   ├── new_jobs.csv    # CSV containing newly discovered jobs from the latest run
│   └── ...             # Raw & normalized HTML logs (for debugging)
├── .env                # Environment variables (do not commit this!)
├── Dockerfile          # Container configuration with chromium and webdriver
├── main2.py            # Main application script
└── requirements.txt    # Python dependencies
```

## 🚀 How It Works

1. **Navigation**: Selenium visits the `TARGET_URL` and grabs the raw HTML.
2. **AI Normalization**: The HTML is heavily truncated and cleaned, then passed to the Gemini LLM. The LLM extracts job details (Title, Qualifications, Location, Link) into a standardized markup and determines how to navigate to the *next* page.
3. **Parsing**: Beautiful Soup parses the normalized output and extracts the job records.
4. **Storage**: Jobs are inserted into an SQLite database. If a job's link already exists in the DB, it is ignored as a duplicate.
5. **Notification**: Any new jobs successfully inserted into the database are logged to a CSV and emailed directly to your inbox!

## 🤝 Contributing
Contributions, issues, and feature requests are welcome!

## 📝 License
This project is open-source and available under the MIT License.
