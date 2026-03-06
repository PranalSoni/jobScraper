from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import os

# Ensures data directory exists before saving files
os.makedirs("data", exist_ok=True)

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
file = 0
for i in range(1, 30):
    driver.get(f"https://www.google.com/about/careers/applications/jobs/results?q=%22Software%20Engineer%22&location=United%20States&page={i}")
    elems = driver.find_elements(By.CLASS_NAME, "sMn82b")
    for elem in elems:
        d = elem.get_attribute("outerHTML")
        with open(f"data/SoftwareEngineer_{file}.html","w", encoding="utf-8") as f:
            f.write(d)
            file += 1
    time.sleep(6)
driver.close()
