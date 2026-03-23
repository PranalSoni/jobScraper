import json
import os
import time
import hashlib
import smtplib
import sqlite3
from typing import Optional, Literal
from urllib.parse import urljoin
from email.message import EmailMessage

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser


load_dotenv()


# ----------------------------
# Config
# ----------------------------
DATA_DIR = "data"
DB_PATH = "data/data.db"
NEW_JOBS_CSV = "data/new_jobs.csv"

os.makedirs(DATA_DIR, exist_ok=True)

API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-3-flash-preview"


# ----------------------------
# Selenium / LLM Helpers
# ----------------------------
def make_driver() -> WebDriver:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=chrome_options)


def make_llm():
    if not API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable.")

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=0.1,
        api_key=API_KEY,
    )


def clean_html_for_llm(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "path"]):
        tag.decompose()
    return str(soup)


def truncate_text(text: str, max_chars: int = 250_000) -> str:
    return text if len(text) <= max_chars else text[:max_chars]


def invoke_with_retry(chain, payload: dict, max_retries: int = 3, base_sleep: float = 15.0):
    last_error = None

    for attempt in range(max_retries):
        try:
            return chain.invoke(payload)
        except Exception as e:
            last_error = e
            msg = str(e)

            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                sleep_for = base_sleep * (attempt + 1)
                print(f"[retry] Gemini quota/rate limit hit. Sleeping {sleep_for:.1f}s before retry...")
                time.sleep(sleep_for)
                continue

            raise

    raise last_error


def safe_click(driver: WebDriver, selector: str) -> bool:
    try:
        elem = driver.find_element(By.CSS_SELECTOR, selector)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", elem)
        return True
    except (NoSuchElementException, ElementClickInterceptedException, Exception):
        return False


# ----------------------------
# LLM Output Schema
# ----------------------------
class PageResult(BaseModel):
    normalized_html: str = Field(
        description="Normalized jobs HTML as a complete <html><body>...</body></html> document."
    )
    action: Literal["click", "url", "stop"] = Field(
        description="How to navigate to the next page."
    )
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector to click if action='click'."
    )
    next_url: Optional[str] = Field(
        default=None,
        description="URL to navigate to if action='url'."
    )
    reason: str = Field(
        description="Short explanation of the pagination decision."
    )


# ----------------------------
# Prompt
# ----------------------------
COMBINED_PROMPT = PromptTemplate.from_template("""
You are given HTML from a careers/jobs page (any company / ATS).

You must do TWO things from the same input HTML:
1. Extract all visible job postings into a normalized HTML format
2. Determine how to go to the NEXT page of job listings

Return ONLY valid JSON using this exact schema:
{format_instructions}

-----------------------------------
NORMALIZED HTML REQUIREMENTS
-----------------------------------
For EACH job posting output this structure inside normalized_html:

<article class="job">
  <h3>JOB TITLE HERE</h3>

  <h4>Minimum qualifications</h4>
  <ul>
    <li>qualification 1</li>
    <li>qualification 2</li>
  </ul>

  <span class="pwO9Dc">
    <span class="r0wTof">Location 1</span>
    <span class="r0wTof">Location 2</span>
  </span>

  <a class="WpHeLc" href="JOB_LINK">Apply</a>
</article>

Rules for normalized_html:
- Include as many postings as you can find on the page.
- If minimum qualifications are not present on this page, output an empty <ul></ul>.
- If location is not present, still output <span class="pwO9Dc"></span>.
- href should be an absolute URL if possible; if not, keep the relative href.
- Output a single HTML document: <html><body> ... </body></html>.
- Do not output scripts/styles.
- normalized_html must be a string containing ONLY HTML, not markdown.

-----------------------------------
PAGINATION RULES
-----------------------------------
For action:
- Use "click" if there is a visible/likely Next button, next arrow, pagination button, or numbered pagination control that should be clicked.
- Use "url" if there is a clear next page link/URL.
- Use "stop" if there is no evidence of another page.

For selector:
- Only provide selector if action="click".
- Prefer stable CSS selectors.
- Do not invent selectors.

For next_url:
- Only provide next_url if action="url".
- If relative, return it as-is.
- Do not invent URLs.

For reason:
- Give a short explanation.

-----------------------------------
CONSTRAINTS
-----------------------------------
- Return ONLY JSON.
- No markdown.
- No commentary outside JSON.
- If something is missing, use null where appropriate.
- Base all output only on the input HTML below.

Base URL:
{base_url}

Already visited URLs:
{visited_urls}

INPUT HTML:
{html}
""")


def process_page(llm, base_url: str, raw_html: str, visited_urls: list[str]) -> PageResult:
    parser = JsonOutputParser(pydantic_object=PageResult)
    chain = COMBINED_PROMPT | llm | parser

    cleaned = truncate_text(clean_html_for_llm(raw_html), 300_000)

    result = invoke_with_retry(
        chain,
        {
            "format_instructions": parser.get_format_instructions(),
            "base_url": base_url,
            "visited_urls": json.dumps(visited_urls, ensure_ascii=False),
            "html": cleaned,
        },
    )

    if isinstance(result, PageResult):
        return result

    return PageResult(**result)


# ----------------------------
# Scraping
# ----------------------------
def collect(url: str, max_pages: int = 10, sleep_s: int = 2):
    driver = make_driver()
    llm = make_llm()

    visited_urls: list[str] = []
    seen_hashes: set[str] = set()

    try:
        driver.get(url)
        time.sleep(3)

        for page_num in range(1, max_pages + 1):
            current_url = driver.current_url

            if current_url in visited_urls:
                print(f"[collect] URL already visited: {current_url}")
                break

            visited_urls.append(current_url)

            raw_html = driver.page_source
            page_hash = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()

            if page_hash in seen_hashes:
                print("[collect] Duplicate page content detected. Stopping.")
                break

            seen_hashes.add(page_hash)

            raw_path = os.path.join(DATA_DIR, f"raw_{page_num:03d}.html")
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw_html)

            try:
                result = process_page(
                    llm=llm,
                    base_url=current_url,
                    raw_html=raw_html,
                    visited_urls=visited_urls,
                )
            except ValidationError as e:
                print(f"[process] Invalid Gemini JSON: {e}")
                break
            except Exception as e:
                print(f"[process] Failed to process page: {e}")
                break

            normalized_path = os.path.join(DATA_DIR, f"normalized_{page_num:03d}.html")
            with open(normalized_path, "w", encoding="utf-8") as f:
                f.write(result.normalized_html)

            print(f"[collect] Saved raw page: {raw_path}")
            print(f"[collect] Saved normalized page: {normalized_path}")
            print(f"[pagination] action={result.action} reason={result.reason}")

            if page_num >= max_pages:
                print("[collect] Reached requested max_pages.")
                break

            if result.action == "stop":
                print("[collect] No more pages found.")
                break

            if result.action == "url" and result.next_url:
                next_url = urljoin(current_url, result.next_url)

                if next_url in visited_urls:
                    print("[collect] Next URL already visited. Stopping.")
                    break

                driver.get(next_url)
                time.sleep(3)
                time.sleep(sleep_s)
                continue

            if result.action == "click" and result.selector:
                clicked = safe_click(driver, result.selector)
                if not clicked:
                    print(f"[collect] Click failed for selector: {result.selector}")
                    break

                time.sleep(3)
                time.sleep(sleep_s)
                continue

            print("[collect] Invalid pagination response. Stopping.")
            break

    finally:
        driver.quit()


# ----------------------------
# Parse normalized HTML files
# ----------------------------
def parse_normalized_jobs(data_dir: str = DATA_DIR) -> list[tuple[str, str, str, str]]:
    jobs: list[tuple[str, str, str, str]] = []

    files = sorted(
        f for f in os.listdir(data_dir)
        if f.startswith("normalized_") and f.endswith(".html")
    )

    if not files:
        print("[parse] No normalized HTML files found.")
        return jobs

    for file in files:
        path = os.path.join(data_dir, file)
        with open(path, "r", encoding="utf-8") as f:
            html_doc = f.read()

        soup = BeautifulSoup(html_doc, "html.parser")
        job_blocks = soup.select("article.job")

        print(f"[parse] {file}: found {len(job_blocks)} job block(s)")

        for block in job_blocks:
            t = block.find("h3")
            title = t.get_text(strip=True) if t else ""

            header = block.find("h4", string=lambda s: s and s.strip() == "Minimum qualifications")
            ul = header.find_next("ul") if header else block.find("ul")

            min_quals = [li.get_text(" ", strip=True) for li in ul.find_all("li")] if ul else []
            min_quals_text = "\n".join(f"- {q}" for q in min_quals)

            container = block.select_one("span.pwO9Dc")
            if container:
                unique_locs = [
                    s.get_text(strip=True).lstrip("; ").strip()
                    for s in container.select("span.r0wTof")
                ]
                unique_locs = [x for x in unique_locs if x]
                location = ", ".join(unique_locs)
            else:
                location = ""

            a_tag = block.find("a", class_="WpHeLc")
            link = a_tag["href"].strip() if a_tag and a_tag.has_attr("href") else ""

            if not link:
                # Skip rows without a stable key for dedupe
                continue

            jobs.append((title, location, min_quals_text, link))

    return jobs


# ----------------------------
# SQLite
# ----------------------------
def save_new_jobs_to_db(
    jobs: list[tuple[str, str, str, str]],
    db_path: str = DB_PATH,
    csv_path: str = NEW_JOBS_CSV,
) -> list[tuple[str, str, str, str]]:
    con = None
    new_rows: list[tuple[str, str, str, str]] = []

    try:
        con = sqlite3.connect(db_path)
        print("[db] DB created/opened")

        cursor = con.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                title TEXT,
                location TEXT,
                minimum_qualifications TEXT,
                link TEXT PRIMARY KEY
            )
        """)
        print("[db] Table ready")

        insert_sql = """
        INSERT INTO jobs (title, location, minimum_qualifications, link)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(link) DO NOTHING
        RETURNING title, location, minimum_qualifications, link;
        """

        for row in jobs:
            cursor.execute(insert_sql, row)
            inserted = cursor.fetchone()
            if inserted:
                new_rows.append(inserted)

        con.commit()
        print(f"[db] Inserted {len(new_rows)} new job(s)")

        if new_rows:
            new_df = pd.DataFrame(
                new_rows,
                columns=["title", "location", "minimum_qualifications", "link"]
            )
            new_df.to_csv(csv_path, index=False)
            print(f"[db] Wrote {len(new_rows)} new job(s) to {csv_path}")

        return new_rows

    except Exception:
        if con is not None:
            try:
                con.rollback()
            except sqlite3.ProgrammingError:
                pass
        raise

    finally:
        if con is not None:
            con.close()
            print("[db] DB closed")


# ----------------------------
# Email
# ----------------------------
def format_job(title: str, location: str, min_quals: str, link: str) -> str:
    return (
        f"Title: {title}\n\n"
        f"Location: {location}\n\n"
        f"Minimum Qualifications:\n{min_quals or '(not listed)'}\n\n"
        f"Apply Here: {link}\n\n"
        + "-" * 60
    )


def send_email(new_rows: list[tuple[str, str, str, str]]):
    sender_email = os.getenv("EMAIL_ADDRESS")
    receiver_email = os.getenv("RECEIVER_EMAIL")
    password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not receiver_email or not password:
        raise ValueError("Email credentials not found in environment variables.")

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = receiver_email

    if new_rows:
        msg["Subject"] = f"{len(new_rows)} New Jobs Found"

        body_lines = [f"Found {len(new_rows)} new job(s) in this run:\n", "-" * 60]
        for title, location, min_quals, link in new_rows:
            body_lines.append(format_job(title, location, min_quals, link))

        msg.set_content("\n".join(body_lines))
    else:
        msg["Subject"] = "No New Jobs Found"
        msg.set_content("No new jobs were added in this run.")

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)

    print("[email] Email sent successfully")


# ----------------------------
# End-to-end pipeline
# ----------------------------
def run_pipeline(url: str, max_pages: int = 10, sleep_s: int = 2):
    collect(url=url, max_pages=max_pages, sleep_s=sleep_s)

    jobs = parse_normalized_jobs(DATA_DIR)
    print(f"[pipeline] Parsed {len(jobs)} total job row(s) from normalized HTML")

    new_rows = save_new_jobs_to_db(jobs, db_path=DB_PATH, csv_path=NEW_JOBS_CSV)

    send_email(new_rows)

    if new_rows:
        print(f"[pipeline] {len(new_rows)} new job(s) added this run")
    else:
        print("[pipeline] No new jobs added this run")


if __name__ == "__main__":
    try:
        url = os.getenv("TARGET_URL")
        if not url:
            raise ValueError("TARGET_URL environment variable is missing.")

        max_pages_str = os.getenv("MAX_PAGES", "10")
        max_pages = int(max_pages_str)

        run_pipeline(url=url, max_pages=max_pages)
        print(f"Saved HTML files into ./{DATA_DIR}/")
    except Exception as e:
        print(f"Error: {e}")