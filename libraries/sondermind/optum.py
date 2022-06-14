# import os
import time
import imaplib
import email
import re
import datetime
from retry import retry

from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver

from libraries import CONFIG, logger as log


class Optum:
    def __init__(self, optum_creds, gmail_creds):
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        if CONFIG.RUN_MODE == "PRD":
            # chromedriver_path = os.path.join(CONFIG.PATHS.BOT, "chromedriver")
            chromedriver_path = "/usr/bin/chromedriver"
        else:
            chromedriver_path = r"C:\Users\kykuc\Downloads\chromedriver_win32\chromedriver.exe"
        log.info(f"Chrome webdriver path = {chromedriver_path}")
        self.browser = webdriver.Chrome(executable_path=chromedriver_path, options=options)
        self.optum_creds = optum_creds
        self.gmail_creds = gmail_creds

    def login(self):
        log.info("Logging to Optum...")
        self.browser.get(self.optum_creds["url"])
        self.browser.maximize_window()
        self.__click_element_when_visible("//a[contains(text(), 'Log In')]")

        self.__input_text_when_element_is_visible("//input[@id='userNameId_input']", self.optum_creds["login"])
        self.__input_text_when_element_is_visible("//input[@id='passwdId_input']", self.optum_creds["password"])
        self.__click_element_when_visible("//input[@id='SignIn']")
        access_code = self._get_gmail_code()
        log.info(f"got access code = {access_code}")
        self.__input_text_when_element_is_visible("//input[@id='EmailText_input']", access_code)
        self.__click_element_when_visible("//input[@id='EmailAccessCodeSubmitButton']")

        log.info("Successfully logged in!")

    def go_to_authorization_number_search_tab(self):
        self.__click_element_when_visible("//div[@id='menu3']", timeout=60)
        self.__click_element_when_visible("//div[@id='authInquiry']/child::div[text()='Auth Inquiry']")
        self.__click_element_when_visible("//a[@rel='tcontent4']")

    def search_by_auth_number(self, auth_num):
        self.__input_text_when_element_is_visible("//input[@id='authNumber']", auth_num)
        self.__click_element_when_visible("//input[@name='psubmit']")

    def is_search_result(self):
        try:
            self.__wait_until_element_is_visible("//table[@id='tableList']", timeout=30)
            return True
        except NoSuchElementException:
            return False

    def get_optum_client_name(self, client_name_sondermind):
        optum_client_name = self.browser.find_element_by_xpath(
            "//table[@id='tableList']/tbody/tr[1]/td[1]/a"
        ).text.strip()
        return optum_client_name

    def go_to_inqury_details(self):
        self.__click_element_when_visible("//table[@id='tableList']/tbody/tr[1]/td[1]/a")

    def get_optum_client_details(self):
        days_sessions = self.browser.find_element_by_xpath(
            "//form[@id='detailFormId']/table/tbody/tr[5]/td[4]"
        ).text.strip()
        start_date = self.browser.find_element_by_xpath(
            "//form[@id='detailFormId']/table/tbody/tr[6]/td[4]"
        ).text.strip()
        end_date = self.browser.find_element_by_xpath("//form[@id='detailFormId']/table/tbody/tr[7]/td[2]").text.strip()
        auth_number = self.browser.find_element_by_xpath(
            "//form[@id='detailFormId']/table/tbody/tr[4]/td[4]"
        ).text.strip()
        data = {
            "days_sessions": days_sessions,
            "start_date": start_date,
            "end_date": end_date,
            "auth_number": auth_number,
        }
        return data

    def __click_element_when_visible(self, locator, timeout=10):
        try:
            self.__wait_until_element_is_visible(locator, timeout)
        except NoSuchElementException:
            raise AssertionError
        else:
            element = self.browser.find_element_by_xpath(locator)
            element.click()

    def __input_text_when_element_is_visible(self, locator, text, timeout=10):
        try:
            self.__wait_until_element_is_visible(locator, timeout)
        except NoSuchElementException:
            raise AssertionError
        else:
            element = self.browser.find_element_by_xpath(locator)
            element.send_keys(text)

    def __wait_until_element_is_visible(self, locator, timeout=10):
        tries = 1
        while tries != timeout:
            try:
                self.browser.find_element_by_xpath(locator)
            except NoSuchElementException:
                tries += 1
                time.sleep(1)
            else:
                return
        raise NoSuchElementException

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
