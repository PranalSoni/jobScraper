FROM python:3.11-slim

# Install Chromium and its WebDriver for Selenium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure the data directory exists for the Render persistent disk mount
RUN mkdir -p /app/data

# Run the script when the container starts
CMD ["python", "main2.py"]
