"""
Name: teams_puppet
Description: A Python package for getting Teams JSON Web Tokens (JWT) using a headless browser.
"""
import json
import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from selenium.common.exceptions import ( TimeoutException )
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

options = webdriver.ChromeOptions()
options.add_argument("--log-level=3")
options.add_argument("--start-maximized")
options.add_argument("--headless=new")
options.add_experimental_option('excludeSwitches', ['enable-logging'])

def click_element_by_xpath(driver, xpath, timeout=30, method='click'):
    """
    Helper function for selenium to click an element by its XPath.
    Finds element twice to avoid StaleElementReferenceException.
    """
    WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    if method == 'click':
        driver.find_element(By.XPATH, xpath).click()
    elif method == 'script':
        driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, xpath))

class AccountError(Exception):
    """Exception raised for errors in the account sign-in process."""

    def __init__(self, message="There was an error with the account sign-in process."):
        self.message = message
        super().__init__(self.message)

class Puppet:
    """
    A class to represent a Teams Puppet user, used to provide tokens for teams.
    """
    def __init__(self, username: str, password: str):
        """
        Initializes a new Teams Puppet user

        :param username: The username for authentication.
        :param password: The password for authentication.
        """

        self.username = username
        self.password = password

        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._schedule_token_refresh()

        self.teams_token = None
        self.loki_token = None

        self.teams_token, self.loki_token = self.fetch_new_tokens()


    def __del__(self):
        """
        Destructor for the Puppet class. Shuts down the scheduler.
        """
        self.scheduler.shutdown()

    def _schedule_token_refresh(self):
        """
        Schedules a token refresh every 5 minutes.
        """
        self.scheduler.add_job(self.check_tokens, 'interval', minutes=5)

    def check_tokens(self):
        """
        Checks the current token, fetching a new one if necessary.
        """
        expiring_soon = datetime.timedelta(minutes=5)

        teams_token = json.loads(self.teams_token)
        loki_token = json.loads(self.loki_token)

        teams_token_expiring_soon = self.time_til_expiration(teams_token) <= expiring_soon
        loki_token_expiring_soon = self.time_til_expiration(loki_token) <= expiring_soon

        if teams_token_expiring_soon or loki_token_expiring_soon:
            self.refresh_tokens()

    def refresh_tokens(self):
        """
        Refreshes the current tokens.
        """
        self.teams_token, self.loki_token = self.fetch_new_tokens()

    def get_token(self, service: str = "teams") -> str:
        """
        Retrieves the current token, fetching a new one if necessary.

        :return: The current or new token for the specified service.
        """

        expiring_soon = datetime.timedelta(minutes=5)

        if service == "teams":
            teams_token = json.loads(self.teams_token)
            if self.time_til_expiration(teams_token) <= expiring_soon:
                self.refresh_tokens()
            return teams_token['secret']

        if service == "loki":
            loki_token = json.loads(self.loki_token)
            if self.time_til_expiration(loki_token) <= expiring_soon:
                self.refresh_tokens()
            return loki_token['secret']

    def time_til_expiration(self, json_token):
        """
        Calculates the time until the tokens expires.
        """

        if not json_token:
            return datetime.timedelta(0)
        expires_on = datetime.datetime.fromtimestamp(int(json_token['expiresOn']))
        return expires_on - datetime.datetime.now()

    def fetch_new_tokens(self):
        """
        Fetches new tokens for the Teams and Loki services.
        :return: The new tokens for the Teams and Loki services as a tuple.
        """
        auth_token, loki_token = None, None

        # Initialize Chrome WebDriver
        executable_path = ChromeDriverManager().install()
        service = ChromeService(executable_path=executable_path)
        driver = webdriver.Chrome(service=service, options=options)

        # Navigate to the Microsoft authentication link
        driver.get("https://teams.microsoft.com")

        # Wait for the input box with placeholder containing 'email' to be present
        email_input = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@type='email']"
            ))
        )
        email_input.send_keys(self.username)

        click_element_by_xpath(
            driver,
            "//input[@value='Next']"
        )

        # Wait for the password input box with placeholder containing 'Password' to be present
        password_input = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((
                    By.XPATH,
                    "//input[contains(@placeholder, 'Password')]"
                ))
        )
        password_input.send_keys(self.password)

        click_element_by_xpath(
            driver,
            "//button[contains(text(),'Sign in')] | //input[@value='Sign in']"
        )

        try:
            WebDriverWait(driver, 30).until(
                lambda driver: driver.find_element(
                    By.XPATH,
                    """
                    //*[contains(text(), 'Stay signed in?') 
                    or contains(text(), 'Sign-in is blocked') 
                    or contains(text(), 'password is incorrect')]
                    """
                )
            )

            if driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Stay signed in?')]"
            ):
                click_element_by_xpath(driver, ".//input[@value='Yes']")

            if driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Sign-in is blocked')]"
            ):
                raise AccountError((
                    "Sign-in is blocked. "
                    "Please try again later or reset account password "
                    f"for user {self.username}."
                ))

            if driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Your account or password is incorrect.')]"
            ):
                raise AccountError(f"Invalid credentials for user {self.username}.")


        except TimeoutException:
            pass

        element_found = False
        attempts = 0
        while not element_found and attempts < 3:
            click_element_by_xpath(
                driver,
                "//button[@aria-label='Chat']",
                method='script'
            )
            click_element_by_xpath(
                driver,
                "//span[contains(text(), '(You)')]/ancestor::li[@aria-haspopup='dialog']",
                method='script'
            )
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//*[contains(text(), 'Contact information')]"
                    ))
                )
                element_found = True
            except TimeoutException:
                attempts += 1

        driver.implicitly_wait(5)

        all_keys = driver.execute_script('return Object.keys(window.localStorage);')

        for key in all_keys:
            if key.lower().endswith('https://loki.delve.office.com//.default--'):
                loki_token = driver.execute_script(f'return window.localStorage.getItem("{key}");')
            if key.lower().endswith('https://outlook.office.com//.default--'):
                auth_token = driver.execute_script(f'return window.localStorage.getItem("{key}");')

        driver.quit()

        return auth_token, loki_token
