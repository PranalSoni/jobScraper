from bs4 import BeautifulSoup
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from sqlite3 import *

#BS4 Logic
d = {'title': [], 'Minimum qualifications': [], 'location' : [], 'link' : []}
try:
    for file in os.listdir("data"):
        with open(f"data/{file}") as f:
            html_doc = f.read()
        soup = BeautifulSoup(html_doc, "html.parser")

        # NEW: each file may contain multiple jobs
    job_blocks = soup.select("article.job") or [soup]  # fallback: treat whole doc as one job

    for block in job_blocks:
        # title
        t = block.find("h3")
        title = t.get_text(strip=True) if t else ""

        # minimum qualifications
        header = block.find("h4", string=lambda s: s and s.strip() == "Minimum qualifications")
        ul = header.find_next("ul") if header else None

        min_quals = [li.get_text(" ", strip=True) for li in ul.find_all("li")] if ul else []
        min_quals_text = "\n".join(f"- {q}" for q in min_quals)

        # location (safe if missing)
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

        # link (NOT Google-specific)
        a_tag = block.find("a", class_="WpHeLc")
        link = a_tag["href"].strip() if a_tag and a_tag.has_attr("href") else ""

        d['title'].append(title)
        d['location'].append(location)
        d['Minimum qualifications'].append(min_quals_text)
        d['link'].append(link)

    # Code for SQLite Database
    con = None
    
    con = connect("data.db")
    print("DB created/Opened!")
    cursor = con.cursor()

    sql = "create table if not exists jobs(title text, location text, minimum_qualifications text, link text primary key)"
    cursor.execute(sql)
    print("Table created!")

    new_rows = []

    insert_sql = """
    INSERT INTO jobs (title, location, minimum_qualifications, link)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(link) DO NOTHING
    RETURNING title, location, minimum_qualifications, link;
    """

    for row in zip(d["title"], d["location"], d["Minimum qualifications"], d["link"]):
        cursor.execute(insert_sql, row)
        inserted = cursor.fetchone()
        if inserted:
            new_rows.append(inserted)

    con.commit()


    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=["title", "location", "minimum_qualifications", "link"])
        new_df.to_csv("new_jobs.csv", index=False)
        print(f"{len(new_rows)} new jobs written to new_jobs.csv")
        print(new_df)

    else:
        print("No new jobs inserted this run.")

    if con is not None:
        con.close()
        print("DB Closed!")

    #email configuration
    sender_email = os.getenv("EMAIL_ADDRESS")
    receiver_email = os.getenv("RECEIVER_EMAIL")
    password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not receiver_email or not password:
        raise ValueError("Email credentials not found in environment variables.")

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = receiver_email

    def format_job(title, location, min_quals, link):
        return (
            f"Title: {title}\n\n"
            f"Location: {location}\n\n"
            f"Minimum Qualifications:\n{min_quals}\n\n"
            f"Apply Here: {link}\n\n"
            + "-" * 60
        )

    if new_rows:
        msg["Subject"] = f"{len(new_rows)} New Google Jobs Found"

        body_lines = [f"Found {len(new_rows)} new job(s) in this run:\n", "-" * 60]
        for (title, location, min_quals, link) in new_rows:
            body_lines.append(format_job(title, location, min_quals, link))

        msg.set_content("\n".join(body_lines))
    else:
        msg["Subject"] = "No New Google Jobs Found"
        msg.set_content("No new jobs were added in this run.")


    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)

    print("Email sent successfully")

except Exception as e:
    print(f"Error: {e}")
    if 'con' in locals() and con is not None:
        try:
            con.rollback()
        except sqlite3.ProgrammingError:
            pass # DB was already closed or not fully opened