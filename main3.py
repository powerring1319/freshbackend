import time
import base64
import re
import pytesseract
import json
import threading
from io import BytesIO
from datetime import datetime
from fastapi import FastAPI, HTTPException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException,
                                        NoSuchElementException,
                                        WebDriverException)
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image, ImageEnhance
from pydantic import BaseModel
from typing import Optional, List

# Constants
URL = "https://gps.freshliance.com/"
EMAIL = "seton@sotechafrica.com"
PASSWORD = "123456"
TARGET_URL = "https://gps.freshliance.com/index"
TABLE_BODY_XPATH = "/html/body/div/div[2]/div/div[1]/div/div[2]/section/div/div[3]/div[1]/div[3]/div[2]/div[3]/table/tbody"
DATA_FILE = "table_data.json"
MAX_LOGIN_ATTEMPTS = 5
SCRAPE_INTERVAL = 60  # seconds


# Pydantic model for response validation
class TableDataResponse(BaseModel):
    status: str
    data: Optional[List[List[str]]]
    updatedAt: Optional[str]
    message: Optional[str]


# Initialize FastAPI
app = FastAPI()
is_scraping_active = False  # Track if scraping is running
driver_lock = threading.Lock()  # Thread lock for driver operations


def setup_driver():
    """Sets up the Chrome WebDriver with improved options."""
    chrome_options = Options()

    # Headless mode configuration
    chrome_options.add_argument("--headless=new")  # New headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # Configure service with automatic driver management
    service = Service(ChromeDriverManager().install())

    # Configure driver with timeout settings
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


def enhance_captcha_image(image):
    """Enhances CAPTCHA image for better OCR recognition."""
    try:
        # Convert to grayscale
        image = image.convert('L')

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)  # Fixed typo: enhancer.enhance()

        # Binarize the image
        image = image.point(lambda x: 0 if x < 140 else 255)
        return image
    except Exception as e:
        print(f"Error enhancing image: {e}")
        return image


def extract_captcha(driver):
    """Extracts CAPTCHA text using OCR with improved reliability."""
    try:
        img_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[3]/div/div/img")))
        img_src = img_element.get_attribute("src")

        match = re.search(r'data:image\/\w+;base64,(.+)', img_src)
        if match:
            base64_data = match.group(1)
            image_bytes = base64.b64decode(base64_data)
            image = Image.open(BytesIO(image_bytes))
            image = enhance_captcha_image(image)

            extracted_text = pytesseract.image_to_string(
                image,
                config="--psm 8 -c tessedit_char_whitelist=0123456789"
            ).strip()

            print(f"Extracted CAPTCHA: {extracted_text}")
            return extracted_text
    except Exception as e:
        print(f"Error extracting CAPTCHA: {e}")
    return None


def login(driver):
    """Attempts to log in with improved reliability and retries."""
    for attempt in range(MAX_LOGIN_ATTEMPTS):
        try:
            print(f"Attempting login (attempt {attempt + 1}/{MAX_LOGIN_ATTEMPTS})")

            # Refresh the page if not first attempt
            if attempt > 0:
                driver.refresh()
                time.sleep(2)

            captcha_text = extract_captcha(driver)
            if not captcha_text:
                print("Failed to extract CAPTCHA")
                continue

            # Fill login form
            email_field = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[1]/div/div[1]/input")))
            email_field.clear()
            email_field.send_keys(EMAIL)

            password_field = driver.find_element(
                By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[2]/div/div[1]/div/input")
            password_field.clear()
            password_field.send_keys(PASSWORD)

            captcha_field = driver.find_element(
                By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[3]/div/div/div/input")
            captcha_field.clear()
            captcha_field.send_keys(captcha_text)

            # Click login button
            login_button = driver.find_element(
                By.XPATH, "/html/body/div/div[2]/div[2]/div/div[1]/form/div[4]/div/button")
            login_button.click()

            # Wait for successful login
            WebDriverWait(driver, 10).until(EC.url_to_be(TARGET_URL))
            print("✅ Login successful!")
            return True

        except TimeoutException:
            print("⚠️ Login timeout - page didn't load as expected")
        except Exception as e:
            print(f"Login attempt {attempt + 1} failed: {str(e)}")
            time.sleep(2)

    return False


def scrape_data():
    """Main scraping function with improved error handling."""
    global is_scraping_active

    while is_scraping_active:
        driver = None
        try:
            with driver_lock:
                driver = setup_driver()
                print("🌐 Navigating to target URL...")
                driver.get(URL)

                if login(driver):
                    print("🔍 Starting data extraction...")
                    extract_table_data(driver)
                else:
                    print("❌ Failed to login after multiple attempts")

        except Exception as e:
            print(f"⚠️ Error in scraping thread: {str(e)}")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

            if is_scraping_active:
                print(f"🔄 Retrying in 10 seconds...")
                time.sleep(10)


def extract_table_data(driver):
    """Extracts table data with improved reliability."""
    global is_scraping_active

    while is_scraping_active:
        try:
            print("🔄 Attempting to fetch table data...")

            # Wait for table to be present
            table_body = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, TABLE_BODY_XPATH)))

            # Get all rows
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            # Extract data from each row
            table_data = []
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                row_data = [cell.text.strip() for cell in cells]
                if row_data:
                    table_data.append(row_data)

            # Prepare JSON data
            json_data = {
                "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": table_data
            }

            # Save to file
            with open(DATA_FILE, "w") as f:
                json.dump(json_data, f, indent=4)

            print(f"✅ Table data updated at {json_data['updatedAt']}")

            # Wait for next scrape
            time.sleep(SCRAPE_INTERVAL)

        except TimeoutException:
            print("⚠️ Timeout while waiting for table data")
            try:
                driver.refresh()
                time.sleep(5)
            except:
                break
        except Exception as e:
            print(f"⚠️ Error in table extraction: {str(e)}")
            break


@app.on_event("startup")
def start_scraping_on_server_start():
    """Starts scraping when the server starts."""
    global is_scraping_active

    if not is_scraping_active:
        print("🚀 Server started, initializing web scraping...")
        is_scraping_active = True
        threading.Thread(
            target=scrape_data,
            daemon=True
        ).start()


@app.on_event("shutdown")
def stop_scraping_on_server_shutdown():
    """Ensures scraping stops when server shuts down."""
    global is_scraping_active
    is_scraping_active = False
    print("🛑 Server shutting down - stopping scraping...")


@app.get("/get_data", response_model=TableDataResponse)
def get_data():
    """API endpoint to fetch the latest extracted table data."""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        return {
            "status": "success",
            "data": data["data"],
            "updatedAt": data["updatedAt"]
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No data available"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving data: {str(e)}"
        )


@app.get("/status")
def get_status():
    """API to check scraping status."""
    return {
        "scraping_active": is_scraping_active,
        "status": "running" if is_scraping_active else "stopped"  # Fixed typo: is_scraping_active
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)