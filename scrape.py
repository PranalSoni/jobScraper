import os
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser


# ----------------------------
# Config
# ----------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

API_KEY = os.getenv("GEMINI_API_KEY", "")  # set env var instead of hardcoding
MODEL_NAME = "gemini-3-flash-preview"


# ----------------------------
# Helpers
# ----------------------------
def make_driver():
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
        temperature=0.3,
        api_key=API_KEY
    )

def clean_html_for_llm(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "path"]):
        tag.decompose()
    return str(soup)

NORMALIZE_PROMPT = PromptTemplate.from_template("""
You are given HTML from a careers/jobs page (any company / ATS).

Return ONLY valid HTML (no markdown, no commentary) that matches this exact structure,
so a BeautifulSoup scraper can parse it:

For EACH job posting output:

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

Rules:
- Include as many postings as you can find on the page.
- If minimum qualifications are not present on this page, output an empty <ul></ul>.
- If location is not present, still output <span class="pwO9Dc"></span>.
- href should be an absolute URL if possible; if not, keep the relative href.
- Output a single HTML document: <html><body> ... </body></html>.
- Do not output scripts/styles.

Base URL: {base_url}

INPUT HTML:
{html}
""")

def normalize_html(llm, base_url: str, raw_html: str) -> str:
    parser = StrOutputParser()
    chain = NORMALIZE_PROMPT | llm | parser

    cleaned = clean_html_for_llm(raw_html)

    # Guardrail against huge pages (still whole page minus scripts/styles).
    MAX_CHARS = 350_000
    if len(cleaned) > MAX_CHARS:
        cleaned = cleaned[:MAX_CHARS]

    return chain.invoke({"base_url": base_url, "html": cleaned})


# ----------------------------
# Main routine
# ----------------------------
def collect(url: str, pages: int = 1, sleep_s: int = 4):
    """
    Generic: loads the same URL `pages` times.
    If you have a known page param, just build the URL inside this loop.
    """
    driver = make_driver()
    llm = make_llm()

    try:
        for i in range(1, pages + 1):
            driver.get(url)
            time.sleep(2)  # allow JS rendering

            raw_html = driver.page_source
            normalized = normalize_html(llm, base_url=url, raw_html=raw_html)

            out_path = os.path.join(DATA_DIR, f"normalized_{i:03d}.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(normalized)

            time.sleep(sleep_s)
    finally:
        driver.quit()


if __name__ == "__main__":
    url = input("Enter any careers/search URL: ").strip()
    collect(url, pages=1)
    print(f"Saved normalized HTML into ./{DATA_DIR}/")