"""
Name: teams_puppet
Description: A Python package for getting Teams JSON Web Tokens (JWT) using a headless browser.
"""

import datetime
import os
import time

import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from selenium.common.exceptions import (NoSuchElementException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from seleniumwire import webdriver
from webdriver_manager.chrome import ChromeDriverManager

options = webdriver.ChromeOptions()
options.add_argument("--log-level=3")
options.add_argument("--headless=new")
options.add_experimental_option('excludeSwitches', ['enable-logging'])

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
        self.schedule_token_refresh()

        self.teams_token = None
        self.loki_token = None

        self.teams_token, self.loki_token = self.fetch_new_tokens()


    def __del__(self):
        """
        Destructor for the Puppet class. Shuts down the scheduler.
        """
        self.scheduler.shutdown()

    def schedule_token_refresh(self):
        """
        Schedules a token refresh every 5 minutes.
        """
        self.scheduler.add_job(self.check_tokens, 'interval', minutes=5)

    def check_tokens(self):
        """
        Checks the current token, fetching a new one if necessary.
        """
        if not self.teams_token or self.time_til_expiration() <= datetime.timedelta(minutes=5):
            self.teams_token, self.loki_token = self.fetch_new_tokens()

    def get_token(self, service: str = "teams") -> str:
        """
        Retrieves the current token, fetching a new one if necessary.

        :return: The current or new token for the specified service.
        """

        if not self.teams_token or self.time_til_expiration() <= datetime.timedelta(minutes=5):
            self.teams_token, self.loki_token = self.fetch_new_tokens()

        if service == "teams":
            return self.teams_token

        if service == "loki":
            return self.loki_token

    def time_til_expiration(self):
        """
        Calculates the time until the token expires.
        """
        if not self.teams_token:
            return datetime.timedelta(seconds=-1)
        try:
            payload = jwt.decode(self.teams_token, options={"verify_signature": False})
            expiration_time = datetime.datetime.fromtimestamp(payload['exp'])
            return expiration_time - datetime.datetime.now()
        except jwt.DecodeError:
            return datetime.timedelta(seconds=-1) 

    def fetch_new_tokens(self):
        """
        Fetches new tokens for the Teams and Loki services.
        :return: The new tokens for the Teams and Loki services as a tuple.
        """
        auth_token, loki_token = None, None

        try:
            # Initialize Chrome WebDriver
            executable_path = ChromeDriverManager().install()
            
            # If exepath is not an exe, find an exe in the same folder as the exefile
            # Until the issue is fixed in the webdriver_manager package
            # https://github.com/SergeyPirogov/webdriver_manager/pull/666
            if not executable_path.endswith(".exe"):
                directory_path = os.path.dirname(executable_path)
                executable_path = os.path.join(directory_path, "chromedriver.exe")

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

            next_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//input[@value='Next']"
                ))
            )
            next_button.click()

            # Wait for the password input box with placeholder containing 'Password' to be present
            password_input = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((
                        By.XPATH,
                        "//input[contains(@placeholder, 'Password')]"
                    ))
            )
            password_input.send_keys(self.password)

            sign_in_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//input[@value='Sign in']"
                ))
            )
            sign_in_button.click()

            try:
                # Wait for the 'Stay signed in?' prompt to be present
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//div[contains(text(), 'Stay signed in?')]"
                    ))
                )
                # Find the 'Yes' button within the prompt and click it
                yes_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        ".//input[@value='Yes']"
                    ))
                )
                yes_button.click()
            except TimeoutException:
                # If the 'Stay signed in?' prompt does not appear, pass
                pass

            auth_token_found = False
            start_time = time.time()
            last_checked_index = 0

            # Loop until the auth token is found or 30 seconds have passed
            while not auth_token_found and time.time() - start_time < 30:
                # Only check new requests
                new_requests = driver.requests[last_checked_index:]
                for request in new_requests:
                    # Access the Authorization header if present
                    auth_header = request.headers.get('Authorization')
                    if auth_header:
                        if "Bearer" not in auth_header:
                            continue
                        if len(auth_header.split(" ")) != 2:
                            continue
                        auth_token = auth_header.split(" ")[1]
                        try:
                            payload = jwt.decode(auth_token, options={"verify_signature": False})
                            if payload["aud"] == "https://api.spaces.skype.com":
                                auth_token_found = True
                                break
                        except jwt.DecodeError:
                            pass
                # Update the last checked index for the next iteration
                last_checked_index = len(driver.requests)
                time.sleep(0.1)

            if not auth_token:
                print("Auth token not found.")
                auth_token = None

            # Get a token for the loki delve endpoint
            profile_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[@aria-label='Your profile, status Available']"
                ))
            )
            profile_button.click()

            view_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[@aria-label='View your profile']"
                ))
            )
            view_button.click()

            # loki.delve.office.com


            loki_token_found = False
            start_time = time.time()
            last_checked_index = 0
            # Loop until the loki token is found or 30 seconds have passed
            while not loki_token_found and time.time() - start_time < 30:
                new_requests = driver.requests[last_checked_index:]
                for request in new_requests:
                    if not request.url.endswith("loki.delve.office.com"):
                        continue
                    auth_header = request.headers.get('Authorization')
                    if auth_header:
                        if "Bearer" not in auth_header:
                            continue
                        if len(auth_header.split(" ")) != 2:
                            continue
                        loki_token = auth_header.split(" ")[1]
                        loki_token_found = True
                        break
                last_checked_index = len(driver.requests)
                time.sleep(0.1)


        except TimeoutException:
            print("TimeoutException: The page took too long to load"
                  " or an element took too long to be available.")
            auth_token = None
        except NoSuchElementException:
            print("NoSuchElementException: The script could not find"
                  " an expected element on the page.")
            auth_token = None
        except WebDriverException as e:
            print("WebDriverException: An error occurred",
                 f" with the WebDriver. Error: {e}")
            auth_token = None
        finally:
            driver.quit()

        return auth_token, loki_token