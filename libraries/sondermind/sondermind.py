import os.path
import time
import re
from datetime import timedelta, date, datetime

from selenium.webdriver.common.keys import Keys
from RPA.Browser.Selenium import Selenium
from selenium.common.exceptions import ElementNotInteractableException
from libraries import CONFIG, logger as log
from ta_captcha_solver.ta_captcha_solver import ImageCaptcha
from libraries.credentials import bit_warden


class SonderMind:
    def __init__(
        self,
        sondermind_credentials: dict,
        gmail_credentials: dict,
        gmail_creds_name: str,
        captcha_key: str,
    ):
        self.browser = Selenium()
        self.credentials = sondermind_credentials
        self.gmail_creds = gmail_credentials
        self.gmail_creds_name = gmail_creds_name
        self.captcha_guru_api_key = captcha_key
        self.home_page_url = "https://admin.sondermind.com/admin/user_management/users"
        self.current_insurance = ""
        self.current_records = []

        self.today = date.today()
        self.num_of_eap_visits = ""
        self.start_date = ""
        self.end_date = ""
        self.num_of_claims = 0
        self.browser_windows = ""
        self.date_format = "%m/%d/%Y"

        self.blank_member_numbers = []
        self.blank_authorization_numbers = []
        self.clients_with_rows_more_than_eap_sessions = []
        self.rows_without_edit_button = []
        self.verified_clients = []

    def solve_captcha(self):
        for _attempts in range(10):
            try:
                self.browser.wait_until_element_is_visible('//img[@id="captchaimg"]')
                self.browser.capture_element_screenshot(
                    '//img[@id="captchaimg"]',
                    filename=f"{CONFIG.PATHS.TEMP}/captcha_screenshot{_attempts}.png",
                )
                captcha_img_path = f"{CONFIG.PATHS.TEMP}/captcha_screenshot{_attempts}.png"
                image_captcha = ImageCaptcha(
                    captcha_guru_api_key=self.captcha_guru_api_key,
                    image_source=captcha_img_path,
                )
                image_captcha.solve()
                self.browser.input_text(
                    '//input[@aria-label="Type the text you hear or see"]',
                    image_captcha.token,
                )
                self.browser.click_element_when_visible('//span[contains(text(), "Next")]')
                time.sleep(5)
                if self.browser.does_page_contain_element('//input[@name="password"]'):
                    break
                else:
                    continue
            except Exception as e:
                if _attempts >= 9:
                    log.warning("Captcha Error")
                    raise Exception(f"Failed to solve captcha. with error {e}")

    def login(self):
        self.browser.open_available_browser(self.credentials["url"])
        self.browser.maximize_browser_window()
        self.browser.input_text_when_element_is_visible(
            '//input[@id="app_authenticate_email"]', self.credentials["login"]
        )
        self.browser.input_text_when_element_is_visible(
            '//input[@id="app_authenticate_password"]', self.credentials["password"]
        )
        l = self.browser.find_element("//h1[@data-test='title-login']")
        log.info(f"Title = {l.text}\n")
        log.info(f"I inputed {self.credentials['password']} to password field, it really exists!!!")
        # log.info(f"\nh1 text = {self.browser.find_element('/html/body/div[3]/div/h1[2]').text}\n")
        self.browser.click_button_when_visible('//button[@type="submit"]')
        try:
            self.browser.click_element_when_visible('//span[contains(text(), "Next")]')
        except Exception as e:
            self.browser.set_screenshot_directory(os.path.join(CONFIG.PATHS.DW, "output"))
            self.browser.capture_page_screenshot()
            print(e)

        self.solve_captcha()
        self.browser.input_text_when_element_is_visible('//input[@name="password"]', self.gmail_creds["password"])
        self.browser.click_element_when_visible('//span[contains(text(), "Next")]')
        tries = 0
        while tries < 5:
            try:
                time.sleep(2)
                self.browser.input_text_when_element_is_visible('//input[@name="totpPin"]', self.gmail_creds["otp"])
                self.browser.wait_until_page_contains_element('//span[contains(text(), "Next")]')
                self.browser.find_element('//span[contains(text(), "Next")]').click()
                self.browser.wait_until_element_is_visible(
                    '//input[@value="Sign in with SonderMind"]',
                    timeout=timedelta(seconds=30),
                )
                break
            except AssertionError:
                time.sleep(3)
                bit_warden.bitwarden_login()
                self.gmail_creds = bit_warden.get_credentials({"gmail": self.gmail_creds_name})["gmail"]
                tries += 1
            except ElementNotInteractableException:
                time.sleep(2)
                self.browser.find_element('//span[contains(text(), "Next")]').click()
                self.browser.wait_until_element_is_visible(
                    '//input[@value="Sign in with SonderMind"]', timeout=timedelta(seconds=30)
                )
                break
        self.browser.click_element_when_visible('//input[@value="Sign in with SonderMind"]')
        log.info("Successfully login on SonderMind")

    def select_insurance(self, insurance_name):
        self.browser.wait_until_page_contains_element("//mat-select", timeout=timedelta(seconds=20))
        self.browser.find_element("//mat-select").click()
        self.browser.wait_until_page_contains_element(f'//span[contains(text(),"{insurance_name}")]')
        self.browser.scroll_element_into_view(f'//span[contains(text(),"{insurance_name}")]')
        self.browser.mouse_down(f'//span[contains(text(),"{insurance_name}")]')
        self.browser.press_keys(None, "ENTER")

    def sort_records(self):
        sort_button = '//th[contains(text()," Days in Queue")]/mat-icon'
        self.browser.wait_until_page_contains_element(sort_button, timeout=timedelta(seconds=15))
        self.browser.double_click_element(sort_button)
        self.browser.wait_until_page_contains_element(
            '//tbody//tr[@class="ng-star-inserted"]', timeout=timedelta(seconds=60)
        )

    def open_record(self, record_index):
        record_locator = f'//tbody//tr[@class="ng-star-inserted"][{record_index}]'
        self.browser.wait_until_page_contains_element(record_locator)
        self.browser.scroll_element_into_view(record_locator)
        self.browser.click_element(record_locator)

    def verify_opened_record(self):
        if CONFIG.RUN_MODE == "PRD":
            self.browser.click_element_when_visible("//span[text()='Verified - Mark as Worked']/parent::button")
            self.browser.wait_until_element_is_not_visible("//span[text()='Verified - Mark as Worked']/parent::button")
        else:
            self.exit_record()

    def is_auth_number_cigna_valid(self, number):
        member_number = str(number)
        res = re.fullmatch("^\d{9}\*0|^\d{9}", member_number)
        # print("Res for ", member_number, "is", res)
        if res:
            date_to_compare = datetime.strptime("April 1", "%B %d").date().replace(year=self.today.year)
            if date_to_compare <= self.today:
                if member_number.startswith(str(self.today.year)[2:]):
                    return True
            elif date_to_compare > self.today:
                if member_number.startswith(str(self.today.year)[2:]) or member_number.startswith(
                    str(self.today.year - 1)[2:]
                ):
                    return True
        return False

    @staticmethod
    def is_auth_number_optum_valid(number):
        res = re.fullmatch(r"\w{6}-1|\w{6}-2", number)
        return res

    @staticmethod
    def get_clean_auth_number_cigna(number):
        if number[-2:] == "*O":
            number = number[:-2]
        return number

    def open_link_in_new_window_and_switch_to_it(self, link):
        self.browser.execute_javascript(f"window.open('{link}');")
        self.browser.switch_window("new")

    def close_current_window_and_switch_to_main(self):
        self.browser.close_window()
        self.browser.switch_window("main")

    def go_to_client_note_tab_and_add_note(self, note_text):
        self.browser.click_element_when_visible("//a[text()='Client Notes']")
        self.browser.click_element_when_visible("//a[text()='Add Note']")
        self.browser.input_text_when_element_is_visible("//textarea[@id='client_note_note']", note_text)
        self.browser.click_element_when_visible("//a[@id='modal_save_button']")
        self.browser.wait_until_element_is_visible("//div[@class='toast toast-success']")

    def set_up_client_for_cash_pay_and_submit_record(self):
        if CONFIG.RUN_MODE == "PRD":
            self.browser.click_element_when_visible("//span[text()='Set up user for cash pay']")
            self.browser.click_element_when_visible("//span[text()='Submit']/parent::button")
            self.browser.wait_until_element_is_not_visible("//span[text()='Submit']/parent::button")
        else:
            self.exit_record()

    def get_element_value(self, locator):
        value = self.browser.find_element(locator).get_attribute("value")
        return value

    def update_edit_insurance_window_with_optum_client_details(self, client_details):
        self.browser.input_text_when_element_is_visible("//input[@id='insurance_eap_company_name']", "Optum")
        self.browser.input_text_when_element_is_visible(
            "//input[@id='insurance_policy_number']", client_details.get("auth_number")
        )
        self.browser.input_text_when_element_is_visible(
            "//input[@id='insurance_eap_session_count']", client_details.get("days_sessions")
        )
        self.browser.input_text_when_element_is_visible(
            "//input[@id='insurance_eap_start_date']", client_details.get("start_date")
        )
        self.browser.input_text_when_element_is_visible(
            "//input[@id='insurance_eap_end_date']", client_details.get("end_date")
        )
        self.browser.click_element_when_visible("//button[text()='Update']")
        self.browser.wait_until_element_is_visible("//p[text()='Insurance updated successfully!']")

    def check_entry(self, index):
        status = True
        try:
            self.browser.click_element_when_visible(
                f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{index}]/td[9]/div/a'
            )
            if not self.browser.does_page_contain_element('xpath://a[@data-modal-title="Edit Insurance"]'):
                log.warning(
                    "%s doesn't contain Edit insurance button"
                    % self.browser.get_text('//*[contains(text(),"Claim #" )]')
                )
                self.rows_without_edit_button.append(self.browser.get_text('//*[contains(text(),"Claim #" )]'))
                status = False
                raise Exception
            self.browser.scroll_element_into_view('xpath://a[@data-modal-title="Edit Insurance"]')
            self.browser.click_element_when_visible('xpath://a[@data-modal-title="Edit Insurance"]')
            self.browser.wait_until_element_is_visible(
                'xpath://*[@id="insurance_auth_notes"]', timeout=timedelta(seconds=15)
            )
            authorization_notes = self.browser.get_text('xpath://*[@id="insurance_auth_notes"]')
            log.info("Auth notes: %s" % authorization_notes)
            self.num_of_eap_visits = self.browser.get_text('xpath://*[@id="insurance_auth_number"]')
            self.start_date = self.browser.get_text('xpath://*[@id="insurance_eap_start_date"]')
            self.end_date = self.browser.get_text('xpath://*[@id="insurance_eap_end_date"]')
            log.info(
                "Insurance details values before: Sessions: %s Start Date: %s End Date: %s"
                % (self.num_of_eap_visits, self.start_date, self.end_date)
            )
            if self.num_of_eap_visits and self.start_date and self.end_date:
                try:
                    self.start_date = datetime.strptime(self.start_date, self.date_format)
                    self.end_date = datetime.strptime(self.end_date, self.date_format)
                except Exception as e:
                    log.exception("Error in converting values of insurance details:" % e)
            else:
                try:
                    self.num_of_eap_visits = re.findall("Sessions:\s\d+", authorization_notes)[0].split()[1]
                    self.start_date = re.findall("Start Date:\s\d+/\d+/\d+", authorization_notes)[0].split()[2]
                    self.end_date = re.findall("End Date:\s\d+/\d+/\d+", authorization_notes)[0].split()[2]
                except IndexError:
                    log.warning("DW cannot recognize variables properly!")
                    self.num_of_eap_visits = ""
                    self.start_date = ""
                    self.end_date = ""
            log.info(
                "Insurance details values after: Sessions: %s Start Date: %s End Date: %s"
                % (self.num_of_eap_visits, self.start_date, self.end_date)
            )
            self.browser.click_element_when_visible('xpath://*[@id="simple_modal"]//button/span')
            self.browser.wait_until_element_is_visible('xpath://a[@data-modal-title="Edit Insurance"]')
        except Exception as e:
            log.exception("Error in check entry function: %s" % e)
        finally:
            self.browser.execute_javascript("window.history.go(-1)")
            self.browser.execute_javascript("window.history.go(-1)")
            self.browser.wait_until_element_is_visible(
                'xpath://*[@id="DataTables_Table_0"]/tbody/tr',
                timeout=timedelta(seconds=15),
            )

            return status

    def check_dos(self, index):
        dos = self.browser.get_text(f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{index}]/td[6]')
        # Is the "DOS" for the row before the "End Date" + 30 days?
        dos = datetime.strptime(dos, self.date_format)
        if (
            self.current_insurance == "Cigna"
            and (dos < datetime.strptime(self.end_date, self.date_format) + timedelta(days=30))
        ) or (
            self.current_insurance == "United Health Care"
            and (dos < datetime.strptime(self.end_date, self.date_format))
        ):
            return True
        return False

    def search_member_number(self, number):
        self.open_link_in_new_window_and_switch_to_it("https://admin.sondermind.com/super_bills")
        self.browser.wait_until_page_contains_element('xpath://*[@id="DataTables_Table_0_length"]/label/select')
        self.browser.select_from_list_by_value('xpath://*[@id="DataTables_Table_0_length"]/label/select', "100")
        self.browser.click_element_when_visible('xpath://*[@id="DataTables_Table_0"]/thead/tr/th[6]')
        self.browser.click_element_when_visible('xpath://*[@id="DataTables_Table_0"]/thead/tr/th[6]')
        self.browser.input_text('xpath://*[@id="DataTables_Table_0_filter"]/label/input', number)
        # might be better with "browser.get_source" instead of time.sleep
        time.sleep(2)
        self.browser.wait_until_element_is_visible(
            'xpath://*[@id="DataTables_Table_0"]/tbody/tr',
            timeout=timedelta(seconds=15),
        )

    def get_insurance_details_row(self, start_index):
        time.sleep(2)
        self.num_of_claims = self.browser.get_element_count('xpath://*[@id="DataTables_Table_0"]/tbody/tr')
        log.info("Row count %s" % self.num_of_claims)
        if not self.browser.does_page_contain_element(
            'xpath://*[@id="DataTables_Table_0"]/tbody/tr/td[text()="No bills found"]'
        ):
            for i in range(start_index, self.num_of_claims + 1):
                id_label = self.browser.get_text(f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{i}]/td/div[2]/span')
                payer_span = self.browser.get_text(f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{i}]/td[4]/span[1]')
                # print("Payer_span", payer_span)
                if (
                    ((self.current_insurance == "Cigna") and (id_label in ["Processing", "Proposed"]))
                    or (self.current_insurance == "United Health Care")
                    and (id_label in ["Processing", "Proposed"])
                    and ("EAP" in payer_span)
                ):
                    return i
        return False

    def check_claim_entries(self):
        status = ""
        try:
            if self.num_of_eap_visits and self.start_date and self.end_date:
                count_processing_proposed = 0
                for i in range(1, self.num_of_claims):
                    id_label = self.browser.get_text(
                        f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{i}]/td/div[2]/span'
                    )
                    payer_span = self.browser.get_text(
                        f'xpath://*[@id="DataTables_Table_0"]/tbody/tr[{i}]/td[4]/span[1]'
                    )
                    if (self.current_insurance == "Cigna" and id_label in ["Processing", "Proposed"]) or (
                        (self.current_insurance == "United Health Care")
                        and (id_label in ["Processing", "Proposed"])
                        and ("EAP" in payer_span)
                    ):
                        count_processing_proposed += 1
                        if self.check_dos(i):
                            continue
                        else:
                            log.info("DOS is after End Date!")
                            status = "Cash pay"
                            break
                if not status and count_processing_proposed <= int(self.num_of_eap_visits):
                    # "Verified - Mark as Worked"
                    status = "Verified"
                    # self.verified_clients.append()
                else:
                    # "Set up user for cash pay"
                    # Client with the number of rows that contain 'Processing' or 'Proposed' status in the 'ID'
                    # is greater than the 'Number of EAP Sessions'
                    status = "Cash pay"
            else:
                # If there's nothing in the Authorization Notes or the DW cannot recognize them properly AND
                # the Number of EAP Sessions and the Authorization End Date fields are blank
                status = "Verified"
                # self.verified_clients.append()
        except Exception as e:
            log.exception("Error in check claim entries: %s" % e)
        finally:
            self.close_current_window_and_switch_to_main()
            return status

    def exit_record(self):
        self.browser.click_button('xpath://span[text()="Cancel"]/parent::button')
        self.browser.wait_until_element_is_not_visible("xpath://mat-dialog-container", timeout=timedelta(seconds=20))

    def process_claim_result(self, result):
        if result == "Cash pay":
            self.set_up_client_for_cash_pay_and_submit_record()
        elif result == "Verified":
            self.verify_opened_record()
        else:
            log.error("Error in process claim result")
            self.exit_record()

    def go_to_insurance_payment_types(self, client_email):
        self.open_link_in_new_window_and_switch_to_it("https://admin.sondermind.com/admin/user_management/users")
        self.browser.click_element_when_visible("//a[text()='Clients']")

        self.browser.wait_until_element_is_enabled("//input[@id='users-search-input']")

        self.browser.find_element("//input[@id='users-search-input']").clear()
        self.browser.find_element("//input[@id='users-search-input']").send_keys(client_email, Keys.ENTER)

        self.browser.wait_until_page_contains(client_email)
        self.browser.wait_until_page_does_not_contain_element("//tbody/tr[3]")

        self.browser.click_link("//td/a[text()='Show']")
        self.browser.click_element_when_visible("//a[text()='Client']")
        self.browser.click_element_when_visible("//a[text()='Insurance Payment types']")

    def get_member_number(self):
        self.browser.wait_until_element_is_visible("//input[@formcontrolname='policy_number']")
        member_number = self.get_element_value("//input[@formcontrolname='policy_number']")
        return member_number
