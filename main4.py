import time
import base64
import re
import pytesseract
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from io import BytesIO

# Configure Tesseract path (update for your system)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Windows
# pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'  # Linux/Mac

# Credentials
USERNAME = "seton@sotechafrica.com"
PASSWORD = "123456"
LOGIN_URL = "https://gps.freshliance.com/"
TARGET_URL = "https://gps.freshliance.com/index"


def setup_driver():
    """Configure Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def preprocess_captcha(image):
    """Enhance CAPTCHA image for better OCR"""
    # Convert to grayscale
    image = image.convert('L')
    # Increase contrast
    image = image.point(lambda x: 0 if x < 140 else 255)
    return image


def solve_captcha(driver):
    """Extract and solve CAPTCHA"""
    try:
        # Wait for CAPTCHA image
        captcha_img = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//img[contains(@src,'base64')]"))
        )

        # Extract base64 image data
        img_src = captcha_img.get_attribute('src')
        base64_data = re.search(r'base64,(.*)', img_src).group(1)
        image_bytes = base64.b64decode(base64_data)

        # Process image
        image = Image.open(BytesIO(image_bytes))
        processed_image = preprocess_captcha(image)

        # OCR with Tesseract
        custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789'
        captcha_text = pytesseract.image_to_string(processed_image, config=custom_config).strip()

        return captcha_text if captcha_text else None

    except Exception as e:
        print(f"CAPTCHA solving failed: {e}")
        return None


def login(driver):
    """Perform login with CAPTCHA handling"""
    driver.get(LOGIN_URL)
    time.sleep(2)  # Allow page to load

    for attempt in range(3):
        try:
            # Solve CAPTCHA
            captcha_text = solve_captcha(driver)
            if not captcha_text:
                print("Failed to solve CAPTCHA, retrying...")
                continue

            # Fill credentials
            driver.find_element(By.XPATH, "//input[@type='email']").send_keys(USERNAME)
            driver.find_element(By.XPATH, "//input[@type='password']").send_keys(PASSWORD)
            driver.find_element(By.XPATH, "//input[@placeholder='CAPTCHA']").send_keys(captcha_text)

            # Submit form
            driver.find_element(By.XPATH, "//button[@type='submit']").click()

            # Verify login success
            WebDriverWait(driver, 10).until(
                lambda d: d.current_url.startswith(TARGET_URL)
            )
            print("Login successful!")
            return True

        except Exception as e:
            print(f"Login attempt {attempt + 1} failed: {e}")
            driver.refresh()
            time.sleep(2)

    return False


# Main execution
if __name__ == "__main__":
    driver = setup_driver()
    try:
        if login(driver):
            print("Successfully logged in!")
            # Add your scraping logic here after login
        else:
            print("Failed to login after multiple attempts")
    finally:
        driver.quit()