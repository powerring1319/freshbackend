import time
import base64
import re
import pytesseract
import json
import threading
from io import BytesIO
from datetime import datetime
from fastapi import FastAPI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image

# Constants
URL = "https://gps.freshliance.com/"
EMAIL = "seton@sotechafrica.com"
PASSWORD = "123456"
TARGET_URL = "https://gps.freshliance.com/index"
TABLE_BODY_XPATH = "/html/body/div/div[2]/div/div[1]/div/div[2]/section/div/div[3]/div[1]/div[3]/div[2]/div[3]/table/tbody"
DATA_FILE = "table_data.json"

# Initialize FastAPI
app = FastAPI()
is_scraping_active = False  # Track if scraping is running


def setup_driver():
    """Sets up the Chrome WebDriver in headless mode for faster processing."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def extract_captcha(driver):
    """Extracts CAPTCHA text using OCR."""
    try:
        img_element = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[3]/div/div/img"))
        )
        img_src = img_element.get_attribute("src")

        match = re.search(r'data:image\/\w+;base64,(.+)', img_src)
        if match:
            base64_data = match.group(1)
            image_bytes = base64.b64decode(base64_data)
            image = Image.open(BytesIO(image_bytes))
            image = image.convert("L").point(lambda x: 0 if x < 140 else 255, '1')  # Enhance contrast
            extracted_text = pytesseract.image_to_string(image,
                                                         config="--psm 8 -c tessedit_char_whitelist=0123456789").strip()
            print(f"Extracted CAPTCHA: {extracted_text}")
            return extracted_text
    except Exception as e:
        print(f"Error extracting CAPTCHA: {e}")
    return None


def login(driver):
    """Attempts to log in and returns True if successful."""
    for _ in range(3):  # Retry login 3 times quickly
        captcha_text = extract_captcha(driver)
        if not captcha_text:
            continue

        try:
            WebDriverWait(driver, 2).until(EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[1]/div/div[1]/input"))).send_keys(EMAIL)
            driver.find_element(By.XPATH,
                                "/html/body/div/div[2]/div[2]/div/div[1]/form/div[2]/div/div[1]/div/input").send_keys(
                PASSWORD)
            driver.find_element(By.XPATH,
                                "/html/body/div/div[2]/div[2]/div/div[1]/form/div[3]/div/div/div/input").send_keys(
                captcha_text)
            driver.find_element(By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[4]/div/button").click()

            WebDriverWait(driver, 5).until(EC.url_to_be(TARGET_URL))
            return True
        except Exception as e:
            print(f"Login attempt failed: {e}")
    return False


def scrape_data():
    """Handles login and continuous scraping."""
    global is_scraping_active
    is_scraping_active = True

    while is_scraping_active:
        driver = setup_driver()
        driver.get(URL)

        if login(driver):
            print("✅ Login successful! Fetching table data...")
            extract_table_data(driver)  # Starts continuous data extraction

        driver.quit()
        time.sleep(3)  # Retry login every 3 seconds if it fails


def extract_table_data(driver):
    """Extracts table data and saves it to a JSON file every minute with an updated timestamp."""
    global is_scraping_active
    while is_scraping_active:
        try:
            table_body = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, TABLE_BODY_XPATH)))
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            table_data = [[cell.text for cell in row.find_elements(By.TAG_NAME, "td")] for row in rows]

            json_data = {
                "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": table_data
            }

            with open(DATA_FILE, "w") as f:
                json.dump(json_data, f, indent=4)

            print(f"✅ Table data updated at {json_data['updatedAt']}")
            time.sleep(60)  # Update every 1 minute
        except Exception as e:
            print(f"Error fetching table data: {e}")
            break


@app.on_event("startup")
def start_scraping_on_server_start():
    """Automatically starts scraping when the server starts."""
    print("🚀 Server started, initializing web scraping...")
    threading.Thread(target=scrape_data, daemon=True).start()


@app.get("/get_data")
def get_data():
    """API endpoint to fetch the latest extracted table data."""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        return {"status": "success", "data": data["data"], "updatedAt": data["updatedAt"]}
    except FileNotFoundError:
        return {"status": "error", "message": "No data available"}


@app.get("/status")
def get_status():
    """API to check if scraping is running."""
    return {"scraping_active": is_scraping_active}
