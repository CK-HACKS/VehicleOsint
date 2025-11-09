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
        except Exception:
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
        try:
            js_click(driver, label_el)
            return True
        except Exception:
            pass

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
                    return True
                except Exception:
                    continue
        except Exception:
            continue
        finally:
            driver.switch_to.default_content()
    return False


def click_proceed_button(driver, wait):
    # try several known ids and fall back to a button with text 'Proceed'
    candidate_ids = ["proccedHomeButtonId", "proceedHomeButtonId", "proceedBtn", "btnProceed"]
    for cid in candidate_ids:
        try:
            btn = wait.until(EC.element_to_be_clickable((By.ID, cid)))
            js_click(driver, btn)
            return True
        except Exception:
            continue

    # fallback: any clickable element with text Proceed
    try:
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Proceed' or normalize-space()='Proceed >'] | //a[normalize-space()='Proceed']")))
        js_click(driver, btn)
        return True
    except Exception:
        return False


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
                try:
                    js_click(driver, btn)
                    return True
                except Exception:
                    return False
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
        # best-effort clear via CDP then cookies
        driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        driver.delete_all_cookies()
    except Exception:
        pass


def _hard_reload(driver):
    try:
        driver.execute_cdp_cmd("Page.reload", {"ignoreCache": True})
    except Exception:
        try:
            driver.refresh()
        except Exception:
            pass


def handle_prev_session_modal(driver, timeout=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        dlg = find_first(driver, [
            "//div[contains(@class,'modal') and contains(@class,'show')]",
            "//div[contains(@class,'ui-dialog') and contains(@style,'display')]"
        ])
        if dlg and "Previous session is already active" in (dlg.text or ""):
            btn = find_first(dlg, [
                ".//button[contains(@class,'btn-close')]",
                ".//button[normalize-space(.)='OK']",
            ])
            if btn:
                try:
                    js_click(driver, btn)
                    return True
                except Exception:
                    return False
        time.sleep(0.1)
    return False


def backend_logout_sweep(driver, origin):
    candidates = ["/vahanservice/logout", "/vahanservice/vahan/logout"]
    for path in candidates:
        try:
            driver.get(origin + path)
            time.sleep(0.25)
        except Exception:
            pass


def wait_for_page_ready(driver, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    time.sleep(0.5)


def main(reg_no, chassis_no_last5):
    start_time = time.time()

    _temp_profile = None
    driver = None

    options = webdriver.ChromeOptions()
    # Use headless mode that works on modern Chrome
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")

    # Disable images via prefs (more reliable)
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    try:
        _temp_profile = _mk_temp_profile()
        options.add_argument(f"--user-data-dir={_temp_profile}")

        result = {
            "success": False,
            "mobile_number": "",
            "error": "",
            "response_time_seconds": 0
        }

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 15)  # reasonable timeout

        homepage_url = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
        driver.get(homepage_url)
        wait_for_page_ready(driver)

        origin = _get_origin(driver.current_url)
        backend_logout_sweep(driver, origin)
        _hard_clear_state(driver, origin)

        driver.get(homepage_url + f"?_cb={int(time.time())}{_rand_suffix()}")
        wait_for_page_ready(driver)

        # Close popup quickly if present
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, "#updatemobileno .btn-close")
            js_click(driver, close_btn)
            time.sleep(0.2)
        except Exception:
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
            except Exception:
                continue

        if not regn_input:
            raise Exception("Could not find registration input field")

        handle_primefaces_checkbox(driver, wait)
        if not click_proceed_button(driver, wait):
            raise Exception("Could not click proceed button")

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
                if not click_proceed_button(driver, wait):
                    raise Exception("Could not click proceed after retry")
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
            except Exception:
                continue

        wait.until(EC.url_contains("form_reschedule_fitness.xhtml"))

        # Enter chassis number
        try:
            chassis_input = driver.find_element(By.ID, "balanceFeesFine:tf_chasis_no")
            chassis_input.clear()
            chassis_input.send_keys(chassis_no_last5)
        except Exception:
            raise Exception("Chassis input not found")

        try:
            validate_button = driver.find_element(By.ID, "balanceFeesFine:validate_dtls")
            js_click(driver, validate_button)
        except Exception:
            # fallback: try to find validate button by text
            vb = find_first(driver, ["//button[contains(.,'Validate')]", "//a[contains(.,'Validate')]"])
            if vb:
                js_click(driver, vb)
            else:
                raise Exception("Validate button not found")

        # Get mobile number with shorter wait
        mobile_number = ""
        for _ in range(8):
            try:
                mobile_input = driver.find_element(By.ID, "balanceFeesFine:tf_mobile")
                mobile_number = mobile_input.get_attribute("value")
                if mobile_number:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if mobile_number:
            result["success"] = True
            result["mobile_number"] = mobile_number
        else:
            result["error"] = "Mobile number field is empty"

    except Exception as e:
        result = locals().get("result", {"success": False, "mobile_number": "", "error": ""})
        result["error"] = f"{type(e).__name__}: {str(e)}"

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if _temp_profile:
            try:
                shutil.rmtree(_temp_profile, ignore_errors=True)
            except Exception:
                pass

        end_time = time.time()
        if "result" not in locals():
            result = {"success": False, "mobile_number": "", "error": "Unknown error", "response_time_seconds": 0}
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
