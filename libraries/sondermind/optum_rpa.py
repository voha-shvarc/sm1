import os
import imaplib
import email
import re
import datetime
import time

from retry import retry

from selenium import webdriver
from RPA.Browser.Selenium import Selenium
from libraries import CONFIG, logger as log


class Optum:
    def __init__(self, optum_creds, gmail_creds):
        if CONFIG.RUN_MODE == "PRD":
            self.chromedriver_path = os.path.join(CONFIG.PATHS.BOT, "chromedriver")
        else:
            self.chromedriver_path = r"C:\Users\kykuc\Downloads\chromedriver_win32\chromedriver.exe"
        log.info(f"Chrome webdriver path = {self.chromedriver_path}")
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--headless")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument('--disable-dev-shm-usage')
        self.browser = Selenium()
        self.optum_creds = optum_creds
        self.gmail_creds = gmail_creds

    def login(self):
        log.info("Logging to Optum...")
        self.browser.open_browser(
            self.optum_creds["url"], browser="googlechrome", executable_path=self.chromedriver_path, options=self.options
        )
        self.browser.maximize_browser_window()
        self.browser.capture_page_screenshot("output/site_page.png")
        self.browser.click_element_when_visible("//a[contains(text(), 'Log In')]")
        time.sleep(2)
        self.browser.capture_page_screenshot("output/login_page.png")
        self.browser.input_text_when_element_is_visible("//input[@id='userNameId_input']", self.optum_creds["login"])
        self.browser.input_text_when_element_is_visible("//input[@id='passwdId_input']", self.optum_creds["password"])
        self.browser.click_element_when_visible("//input[@id='SignIn']")
        access_code = self._get_gmail_code()
        log.info(f"got access code = {access_code}")
        self.browser.input_text_when_element_is_visible("//input[@id='EmailText_input']", access_code)
        self.browser.click_element_when_visible("//input[@id='EmailAccessCodeSubmitButton']")
        log.info("Successfully logged in!")

    @retry(tries=4)
    def _get_gmail_code(self):
        smtp_user = self.gmail_creds["login"]
        smtp_password = self.gmail_creds["App Password"]
        server = "smtp.gmail.com"
        # port = 587
        mail = imaplib.IMAP4_SSL(server)
        mail.login(smtp_user, smtp_password)
        mail.select("inbox")
        data = mail.search(None, "ALL")
        mail_ids = data[1]
        id_list = mail_ids[0].split()
        first_email_id = int(id_list[0])
        latest_email_id = int(id_list[-1])
        for i in range(latest_email_id, first_email_id, -1):
            data = mail.fetch(str(i), "(RFC822)")
            for response_part in data:
                arr = response_part[0]
                if isinstance(arr, tuple):
                    msg = email.message_from_string(str(arr[1], "utf-8"))
                    subject = msg["subject"]
                    received = datetime.datetime.strptime(
                        (re.findall("[0-9]{1,2} [A-Za-z]{3} [0-9]{4}", msg["Received"])[0]).lower(), "%d %b %Y"
                    )
                    if subject == "Access Code Notification" and received.date() == datetime.date.today():
                        msg = str(msg)
                        code = msg.split('<span class="textRegularBold">')[1].split("</span>")[0].strip()
                        return code
        raise ValueError
