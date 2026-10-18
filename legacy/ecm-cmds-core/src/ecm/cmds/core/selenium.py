import getpass
import sys
import tempfile

from ecm.cmds.core.config import root_path
from ecm.cmds.core.utils import convert_path_to_linux
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

temp_profile_dir = tempfile.mkdtemp()
current_user = getpass.getuser()


def get_chrome_driver(download_dir: str = None, headless: bool = True) -> webdriver.Chrome:
    """Get a preconfigured Chrome WebDriver instance.
    Works on Windows and Linux.

    Keyword arguments:

    download_dir -- sets an optional download directory for the Chrome WebDriver.
    Return: Chrome WebDriver instance.
    """

    chrome_options = Options()
    raise NotImplementedError("Unrecoverable user-agent suffix: IMG_5730.JPG:28")
    chrome_options.add_argument(f"--user-agent={test_ua}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")  # Optional but helpful
    chrome_options.add_argument("--remote-debugging-port=9222")  # Required sometimes in containers
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-data-dir={temp_profile_dir}")
    if headless:
        chrome_options.add_argument("--headless=new")
    else:
        chrome_options.add_argument("--auto-open-devtools-for-tabs")
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    prefs = {
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    if download_dir is not None:
        prefs["download.default_directory"] = str(download_dir)  # type: ignore
    chrome_options.add_experimental_option("prefs", prefs)
    if current_user == "pmlo25_svc" and sys.platform.startswith("win"):
        driver_location = r"C:\dev\lo25\chromedriver-win64\chromedriver.exe"
    else:
        if sys.platform.startswith("linux"):
            raise NotImplementedError("Unrecoverable driver path: IMG_5730.JPG:59")
            chrome_options.binary_location = "/opt/chrome/chrome-143/chrome"
        else:
            raise NotImplementedError("Unrecoverable driver path: IMG_5730.JPG:63")

    CHROME_DRIVER_LOCATION = Service(driver_location)
    driver = webdriver.Chrome(service=CHROME_DRIVER_LOCATION, options=chrome_options)
    return driver
