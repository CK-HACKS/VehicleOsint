import sys
import time
import tempfile
import shutil
import random
import string
import json
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def js_click(driver, el):
    driver.execute_script("arguments[0].click();", el)


def find_first(driver_or_el, xpaths):
    for xp in xpaths:
        try:
            els = driver_or_el.find_elements(By.XPATH, xp)
            if els:
                return els[0]
        except:
            continue
    return None


def handle_primefaces_checkbox(driver, wait):
    # Try to find and click the checkbox directly without frame switching first
    label_el = find_first(driver, [
        "//label[contains(normalize-space(.), 'Privacy Policy') or contains(normalize-space(.), 'Terms of Service')]",
        "//label[contains(normalize-space(.), 'Privacy') or contains(normalize-space(.), 'Terms')]",
        "//div[contains(@class,'ui-chkbox')]//div[contains(@class,'ui-chkbox-box')]"
    ])
    if label_el:
        js_click(driver, label_el)
        return

    # Fallback to frame switching only if needed
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for fr in frames:
        driver.switch_to.default_content()
        try:
            driver.switch_to.frame(fr)
            checkbox_elements = [
                "//div[contains(@class,'ui-chkbox')]//div[contains(@class,'ui-chkbox-box')]",
                "//label[contains(normalize-space(.), 'Privacy')]",
                "//input[@type='checkbox']"
            ]
            for xpath in checkbox_elements:
                try:
                    el = driver.find_element(By.XPATH, xpath)
                    js_click(driver, el)
                    driver.switch_to.default_content()
                    return
                except:
                    continue
        except:
            continue
        finally:
            driver.switch_to.default_content()


def click_proceed_button(driver, wait):
    proceed_btn = wait.until(EC.element_to_be_clickable((By.ID, "proccedHomeButtonId")))
    js_click(driver, proceed_btn)


def handle_any_dialog_and_proceed(driver, wait, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        dlg = find_first(driver, [
            "//div[contains(@class,'ui-dialog') and contains(@style,'display') and not(contains(@style,'display: none'))]",
            "//div[contains(@class,'modal') and contains(@class,'show')]",
        ])
        if dlg:
            btn = find_first(dlg, [
                ".//button[normalize-space(.)='Proceed']",
                ".//a[normalize-space(.)='Proceed']",
                ".//span[normalize-space(.)='Proceed']/ancestor::button[1]",
                ".//button[contains(@class,'btn') and contains(.,'Proceed')]",
            ])
            if btn:
                js_click(driver, btn)
                return True
        time.sleep(0.1)
    return False


def _mk_temp_profile():
    return tempfile.mkdtemp(prefix="vh_profile_")


def _rand_suffix(n=4):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def _get_origin(url):
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def _hard_clear_state(driver, origin):
    try:
        driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        driver.delete_all_cookies()
    except Exception:
        pass


def _hard_reload(driver):
    try:
        driver.execute_cdp_cmd("Page.reload", {"ignoreCache": True})
    except Exception:
        driver.refresh()


def handle_prev_session_modal(driver, timeout=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        dlg = find_first(driver, [
            "//div[contains(@class,'modal') and contains(@class,'show')]",
            "//div[contains(@class,'ui-dialog') and contains(@style,'display')]"
        ])
        if dlg and "Previous session is already active" in dlg.text:
            btn = find_first(dlg, [
                ".//button[contains(@class,'btn-close')]",
                ".//button[normalize-space(.)='OK']",
            ])
            if btn:
                js_click(driver, btn)
                return True
        time.sleep(0.1)
    return False


def backend_logout_sweep(driver, origin):
    candidates = ["/vahanservice/logout", "/vahanservice/vahan/logout"]
    for path in candidates:
        try:
            driver.get(origin + path)
            time.sleep(0.3)
        except Exception:
            pass


def wait_for_page_ready(driver, timeout=15):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    time.sleep(0.5)  # Reduced wait time


def main(reg_no, chassis_no_last5):
    start_time = time.time()
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-images")  # Disable images for faster loading
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")

    _temp_profile = _mk_temp_profile()
    options.add_argument(f"--user-data-dir={_temp_profile}")

    result = {
        "success": False, 
        "mobile_number": "", 
        "error": "",
        "response_time_seconds": 0
    }

    try:
        # Use shorter timeouts
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 15)  # Reduced from 30 to 15 seconds

        homepage_url = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
        driver.get(homepage_url)
        wait_for_page_ready(driver)

        origin = _get_origin(driver.current_url)
        backend_logout_sweep(driver, origin)
        _hard_clear_state(driver, origin)
        
        driver.get(homepage_url + f"?_cb={int(time.time())}{_rand_suffix()}")
        wait_for_page_ready(driver)

        # Close popup quickly
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, "#updatemobileno .btn-close")
            js_click(driver, close_btn)
            time.sleep(0.2)
        except:
            pass

        # Find registration input with multiple fast attempts
        regn_input = None
        selectors = [
            (By.ID, "regnid"),
            (By.NAME, "regnid"),
            (By.XPATH, "//input[contains(@id, 'regn')]"),
            (By.XPATH, "//input[contains(@name, 'regn')]"),
            (By.XPATH, "//input[@placeholder]")
        ]
        
        for selector, value in selectors:
            try:
                regn_input = driver.find_element(selector, value)
                if regn_input:
                    regn_input.clear()
                    regn_input.send_keys(reg_no)
                    break
            except:
                continue

        if not regn_input:
            raise Exception("Could not find registration input field")

        handle_primefaces_checkbox(driver, wait)
        click_proceed_button(driver, wait)

        if handle_prev_session_modal(driver):
            _hard_clear_state(driver, origin)
            _hard_reload(driver)
            time.sleep(0.5)

        handle_any_dialog_and_proceed(driver, wait, timeout=8)

        # Wait for URL change with shorter timeout
        try:
            wait.until(EC.url_contains("login.xhtml"))
        except TimeoutException:
            if handle_prev_session_modal(driver):
                _hard_clear_state(driver, origin)
                driver.get(homepage_url + f"?_cb={int(time.time())}{_rand_suffix()}")
                handle_primefaces_checkbox(driver, wait)
                click_proceed_button(driver, wait)
                wait.until(EC.url_contains("login.xhtml"))
            else:
                raise

        # Click fitness icon
        fitness_xpaths = [
            "//a[.//div[contains(text(), 'Re-Schedule Renewal of Fitness Application')]]",
            "//a[contains(@href, 'fitness')]",
            "//a[.//div[contains(text(), 'Fitness')]]"
        ]
        for xpath in fitness_xpaths:
            try:
                fitness_icon = driver.find_element(By.XPATH, xpath)
                js_click(driver, fitness_icon)
                break
            except:
                continue

        wait.until(EC.url_contains("form_reschedule_fitness.xhtml"))
        
        # Enter chassis number
        chassis_input = driver.find_element(By.ID, "balanceFeesFine:tf_chasis_no")
        chassis_input.send_keys(chassis_no_last5)

        validate_button = driver.find_element(By.ID, "balanceFeesFine:validate_dtls")
        js_click(driver, validate_button)

        # Get mobile number with shorter wait
        mobile_number = ""
        for _ in range(5):  # Reduced from 10 to 5 attempts
            try:
                mobile_input = driver.find_element(By.ID, "balanceFeesFine:tf_mobile")
                mobile_number = mobile_input.get_attribute("value")
                if mobile_number:
                    break
            except:
                pass
            time.sleep(0.5)

        if mobile_number:
            result["success"] = True
            result["mobile_number"] = mobile_number
        else:
            result["error"] = "Mobile number field is empty"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    finally:
        if 'driver' in locals():
            try:
                driver.quit()
            except:
                pass
        try:
            shutil.rmtree(_temp_profile, ignore_errors=True)
        except Exception:
            pass
        
        end_time = time.time()
        result["response_time_seconds"] = round(end_time - start_time, 2)
        
        print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        result = {
            "success": False, 
            "mobile_number": "", 
            "error": "Usage: python script.py <REG_NO> <CHASSIS_LAST5>",
            "response_time_seconds": 0
        }
        print(json.dumps(result))
        sys.exit(1)

    main(sys.argv[1].upper(), sys.argv[2])