import os

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as conditions
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = os.getenv("DEALINTERFACE_BASE_URL", "http://127.0.0.1:4173")


@pytest.fixture()
def browser():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1000")
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()


def test_operator_can_open_a_module_workspace(browser):
    browser.get(BASE_URL)
    wait = WebDriverWait(browser, 10)

    wait.until(conditions.visibility_of_element_located((By.TAG_NAME, "h1")))
    browser.find_element(By.XPATH, "//button[normalize-space()='DEALHost']").click()

    wait.until(conditions.url_contains("#/modules/dealhost/"))
    assert browser.find_element(By.CSS_SELECTOR, "main").is_displayed()
    assert browser.find_element(By.XPATH, "//button[normalize-space()='Deployments']").get_attribute("aria-current") == "page"


def test_mobile_layout_has_no_horizontal_page_overflow(browser):
    browser.set_window_size(390, 844)
    browser.get(f"{BASE_URL}/#/modules/dealiot/devices")
    wait = WebDriverWait(browser, 10)

    wait.until(conditions.visibility_of_element_located((By.TAG_NAME, "main")))
    viewport = browser.execute_script("return window.innerWidth")
    page_width = browser.execute_script("return document.documentElement.scrollWidth")

    assert page_width <= viewport + 1
    assert browser.find_element(By.XPATH, "//button[normalize-space()='Device configuration']").is_displayed()
