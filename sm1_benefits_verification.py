from datetime import timedelta

import selenium.common.exceptions

from libraries import CONFIG, CREDENTIALS, logger as log
from supervisor.dynamic import step
from libraries.google_sheets import GoogleSheets
from libraries.sondermind import Optum
from libraries.exceptions import NoMemberNumberException
from libraries.reports import Report, ReportItem
from libraries.google.gmail_Service import GoogleMail
from libraries.sondermind import SonderMind


class Sm1BenefitsVerification:
    @step(1)
    def __init__(self):
        self._sondermind_website = SonderMind(
            CREDENTIALS["sondermind"],
            CREDENTIALS["gmail"],
            "Gmail Account",
            CREDENTIALS["captcha"]["CAPTCHA_API_KEY"],
        )
        self._current_row_index = 1
        self._current_member_number = ""
        self._claim_result = ""
        self._report = Report()
        self._report_item = ReportItem()

        if CONFIG.RUN_MODE == "DEV":
            sheet_id = CREDENTIALS["gmail"]["Test Authorization Template Sheet Id"]
        else:
            sheet_id = CREDENTIALS["gmail"]["Authorization Template Sheet Id"]
        self.google_sheets: GoogleSheets = GoogleSheets(sheet_id)

    @step(1, 1)
    def login_to_sondermind(self):
        """
        Login to Sondermind using the Bitwarden credentials
        """
        # log.info(f"\n{os.listdir('/usr/bin')}\n")
        self._sondermind_website.login()
        # optum_website = Optum(CREDENTIALS["optum"], CREDENTIALS["gmail"])
        # try:
        #     optum_website.login()
        # except Exception as e:
        #     log.info(f"{e}, taking screenshot")
        #     optum_website.browser.capture_page_screenshot()
        # self._sondermind_website.login()

    @step(1, 2)
    def go_to_benefits_verification(self):
        """
        Click "Claims"
        Click "Benefit Verifications"
        """
        current_location = self._sondermind_website.browser.location
        if current_location != CONFIG.BENEFIT_VERIFICATION_URL:
            self._sondermind_website.browser.go_to(CONFIG.BENEFIT_VERIFICATION_URL)

    @step(2)
    def start_insurance_loop(self):
        """
        Repeat from here to process both "Cigna" and "Optum"
        Click "Select Insurance" to expand dropdown
        Has the DW processed Cigna?
            Y - Click "United Health Care", continue with Step Start Loop for Records in Queue
            N - Click "Cigna", continue with Step Start Loop for Records in Queue
        """
        for insurance in CONFIG.INSURANCE_LIST:
            self._report_item.claim_type = insurance
            self._sondermind_website.current_insurance = insurance
            self._sondermind_website.select_insurance(insurance)
            log.info(f"\nProcessing {insurance}...")
            self.start_record_loop()
        self.google_sheets.send_clients_info_to_sheet()

    def _empty_report_item(self):
        self._report_item.set_for_cash_pay = None
        self._report_item.verified_mark_as_worked = None
        self._report_item.blank_member_numbers = None
        self._report_item.processing_or_processed_row = None
        self._report_item.row_without_edit_button = None
        self._report_item.blank_authorization_numbers = None

    def get_client_name(self):
        tries = 0
        client_name = ""
        while tries < 5:
            try:
                self._sondermind_website.browser.scroll_element_into_view(
                    f'//tbody//tr[@class="ng-star-inserted"][{self._current_row_index}]//td[2]'
                )
                client_name = self._sondermind_website.browser.find_element(
                    f'//tbody//tr[@class="ng-star-inserted"][{self._current_row_index}]//td[2]'
                ).text
                break
            except selenium.common.exceptions.StaleElementReferenceException:
                log.exception("Failed to get EAP value for row %s.\nRetrying...." % self._current_row_index)
                tries += 1
        return client_name

    @step(3)
    def start_record_loop(self):
        """
        Start Loop for Records in Queue
        """
        try:
            self.sort_record()
            total_number_of_records = len(
                self._sondermind_website.browser.find_elements('//tbody//tr[@class="ng-star-inserted"]')
            )
            for row_index in range(1, total_number_of_records):
                self._empty_report_item()
                self._current_row_index = row_index
                self._report_item.client = self.get_client_name()
                if self.check_eap():
                    self._sondermind_website.open_record(row_index)
                    if self._sondermind_website.current_insurance == "Cigna":
                        log.info("Processing Cigna-EAP...")
                        self.start_loop_for_cigna()
                    else:
                        log.info("Processing Optum-EAP...")
                        self.start_loop_for_optum()
                self._report.add_row(self._report_item)
            self._sondermind_website.browser.reload_page()
        except Exception as e:
            log.exception(f"Error: {e}")

    @step(3, 1)
    def sort_record(self):
        """
        Continue in Sondermind
        Wait for records to load
        Click "Days in Queue" twice to sort in descending order
        """
        self._sondermind_website.sort_records()
        self._sondermind_website.browser.wait_until_page_contains_element(
            '//tr[@class="ng-star-inserted"]', timeout=timedelta(seconds=60)
        )

    @step(3, 2)
    def check_eap(self):
        """
        Check the EAP value of current record.
        """
        tries = 0
        eap_value = "false"
        while tries < 5:
            try:
                self._sondermind_website.browser.scroll_element_into_view(
                    f'//tbody//tr[@class="ng-star-inserted"][{self._current_row_index}]//td[5]'
                )
                eap_value = self._sondermind_website.browser.find_element(
                    f'//tbody//tr[@class="ng-star-inserted"][{self._current_row_index}]//td[5]'
                ).text
                break
            except selenium.common.exceptions.StaleElementReferenceException:
                log.exception("Failed to get EAP value for row %s.\nRetrying...." % self._current_row_index)
                tries += 1

        if eap_value == "true":
            return True
        else:
            return False

    @step(4)
    def start_loop_for_cigna(self):
        try:
            self._report_item.blank_member_numbers = False
            if self.check_member_number_cigna():
                log.info("Number satisfy requirements: %s" % self._current_member_number)
                self.get_insurance_details_cigna()
                self.check_entries_cigna()
                if self._claim_result:
                    if self._claim_result == "Verified":
                        self._report_item.processing_or_processed_row = True
                        self._report_item.verified_mark_as_worked = True
                    else:
                        self._report_item.set_for_cash_pay = True
                    log.info("Claim result: %s" % self._claim_result)
                    self._sondermind_website.process_claim_result(self._claim_result)
                else:
                    log.warning("Error in claim result")
                    self._sondermind_website.exit_record()
            else:
                log.info(f"Member number {self._current_member_number} is invalid. Setting up client for cash pay...")
                self._report_item.set_for_cash_pay = True
                self._sondermind_website.set_up_client_for_cash_pay_and_submit_record()
        except NoMemberNumberException:
            self._report_item.blank_member_numbers = True
            client_email = self.get_client_email_cigna()
            if not client_email:
                self._report_item.blank_client_email = True
                log.info("No member number and client email is present, adding to the report...")
                self._sondermind_website.exit_record()
                return
            log.info(f"Member number of the user with email {client_email} is empty")
            self._sondermind_website.go_to_insurance_payment_types(client_email)
            self.check_insurance_rows_cigna()

    @step(4, 1)
    def check_member_number_cigna(self):
        self._current_member_number = self._sondermind_website.get_member_number()
        if self._current_member_number:
            if self._sondermind_website.is_auth_number_cigna_valid(self._current_member_number):
                return True
            else:
                return False
        else:
            raise NoMemberNumberException

    @step(4, 2)
    def get_insurance_details_cigna(self):
        """
        Check whether the row contains Processing or Proposed in ID column and
         get number of Visits, Start Date and End Date
        """
        self._sondermind_website.search_member_number(self._current_member_number)
        row = 0
        for tries in range(100):
            row = self._sondermind_website.get_insurance_details_row(row + 1)
            if row:
                if self._sondermind_website.check_entry(row):
                    break
                else:
                    log.info("No edit button! Try: %s" % tries)
            else:
                log.info("No bills found that satisfy Proposed, Processing for num: %s" % self._current_member_number)
                break

    @step(4, 3)
    def check_entries_cigna(self):
        """
        Check whether DOS of the row before End Date + 30 days and
        number of rows with Processing or Proposed status in the ID less than the number of Visits
        """
        self._claim_result = self._sondermind_website.check_claim_entries()

    @step(4, 4)
    def get_client_email_cigna(self):
        # TODO paste client email element's id
        # client_email = self._sondermind_website.browser.find_element("//input[@id='']").get_attribute("value")
        client_email = ""
        return client_email

    @step(4, 5)
    def check_insurance_rows_cigna(self):
        """ """
        self._sondermind_website.browser.wait_until_element_is_visible("//table[@class='table table-striped']")

        insurance_row_xpath = "//tr[@class='insurance-card ']"
        insurance_rows = self._sondermind_website.browser.find_elements(insurance_row_xpath)
        processed_eap = False
        for index in range(len(insurance_rows)):
            processed_eap = False
            insurance_title = self._sondermind_website.browser.find_element(
                f"{insurance_row_xpath}[{index + 1}]/td[1]/span[1]"
            ).text
            if "EAP" in insurance_title:
                if not self._sondermind_website.browser.is_element_visible(  # doesn't contain DELETED
                    f"{insurance_row_xpath}[{index + 1}]/td[1]/span[@class='badge badge-warn']"
                ):
                    log.info("Found the EAP insurance")
                    self._sondermind_website.browser.click_element_when_visible("//a[text()='Edit']")
                    self.check_authorization_number_cigna()
                    processed_eap = True
        if not processed_eap:
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._sondermind_website.exit_record()

    @step(4, 6)
    def check_authorization_number_cigna(self):
        self._sondermind_website.browser.wait_until_element_is_visible("//input[@id='insurance_auth_number']")
        auth_number = self._sondermind_website.browser.find_element(
            "//input[@id='insurance_auth_number']"
        ).get_attribute("value")

        if auth_number:
            log.info(f"Found the auth_number {auth_number}\n")
            if self._sondermind_website.is_auth_number_cigna_valid(auth_number):
                clean_auth_num = self._sondermind_website.get_clean_auth_number_cigna(auth_number)
                self._sondermind_website.browser.input_text_when_element_is_visible(
                    "//input[@id='insurance_eap_company_name']", "Cigna"
                )
                self._sondermind_website.browser.input_text_when_element_is_visible(
                    "//input[@id='insurance_policy_number']", clean_auth_num
                )

                self._sondermind_website.browser.click_element_when_visible("//button[text()='Update']")
                self._sondermind_website.browser.wait_until_element_is_visible(
                    "//p[text()='Insurance updated successfully!']"
                )
                self._sondermind_website.browser.click_element_when_visible(
                    "//a[text()='Basic' and contains(@href, 'edit')]"
                )

                self._sondermind_website.browser.wait_until_element_is_enabled("//input[@id='user_first_name']")
                legal_first_name = self._sondermind_website.get_element_value("//input[@id='user_birth_date']")
                legal_last_name = self._sondermind_website.get_element_value("//input[@id='user_last_name']")
                date_of_birth = self._sondermind_website.get_element_value("//input[@id='user_birth_date']")
                self.google_sheets.add_client_info(legal_first_name, legal_last_name, date_of_birth, auth_number)

                self._sondermind_website.close_current_window_and_switch_to_main()

                self._sondermind_website.browser.input_text_when_element_is_visible(
                    "//input[@formcontrolname='policy_number']", clean_auth_num
                )
                self._report_item.verified_mark_as_worked = True
                self._sondermind_website.verify_opened_record()
                return
            else:
                log.info(f"Auth_number {auth_number} is invalid")

            # if authorization number is not valid or no search result at optum site or clients name are not the same
            log.info("Making note and setting up client for cash pay...")
            self._sondermind_website.browser.click_element_when_visible(
                "//span[text()=' ×']/parent::button[@class='close']"
            )
            self._sondermind_website.go_to_client_note_tab_and_add_note("Invalid EAP Authorization number")
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._report_item.set_for_cash_pay = True
            self._sondermind_website.set_up_client_for_cash_pay_and_submit_record()
        else:
            log.info("No auth number was found, verifying the record")
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._report_item.verified_mark_as_worked = True
            self._sondermind_website.verify_opened_record()

    @step(5)
    def start_loop_for_optum(self):
        try:
            if self.check_member_number_optum():
                log.info("Number satisfy requirements: %s" % self._current_member_number)
                self.get_insurance_details_optum()
                self.check_entries_optum()
                if self._claim_result:
                    log.info("Claim result: %s" % self._claim_result)
                    if self._claim_result == "Verified":
                        self._report_item.processing_or_processed_row = True
                        self._report_item.verified_mark_as_worked = True
                    else:
                        self._report_item.set_for_cash_pay = True
                    self._sondermind_website.process_claim_result(self._claim_result)
                else:
                    log.warning("Error in claim result")
                    self._sondermind_website.exit_record()
            else:
                log.info(f"Member number {self._current_member_number} is invalid. Setting up client for cash pay...")
                self._sondermind_website.set_up_client_for_cash_pay_and_submit_record()
                self._report_item.set_for_cash_pay = True
        except NoMemberNumberException:
            self._report_item.blank_member_numbers = True
            client_email = self.get_client_email_optum()
            if not client_email:
                self._report_item.blank_client_email = True
                log.info("No member number and client email is present, adding to the report...")
                self._sondermind_website.exit_record()
                return
            log.info(f"Member number of the user with email {client_email} is empty")
            self._sondermind_website.go_to_insurance_payment_types(client_email)
            self.check_insurance_rows_optum()

    @step(5, 1)
    def check_member_number_optum(self):
        self._current_member_number = self._sondermind_website.get_member_number()
        if self._current_member_number:
            if self._sondermind_website.is_auth_number_optum_valid(self._current_member_number):
                return True
            else:
                return False
        else:
            raise NoMemberNumberException

    @step(5, 2)
    def get_insurance_details_optum(self):
        """
        Check whether the row contains Processing or Proposed in ID column and
         get number of Visits, Start Date and End Date
        """
        self._sondermind_website.search_member_number(self._current_member_number)
        row = 0
        for tries in range(100):
            row = self._sondermind_website.get_insurance_details_row(row + 1)
            if row:
                if self._sondermind_website.check_entry(row):
                    break
                else:
                    log.info("No edit button! Try: %s" % tries)
            else:
                log.info("No bills found that satisfy Proposed, Processing for num: %s" % self._current_member_number)
                break

    @step(5, 3)
    def check_entries_optum(self):
        """
        Check whether DOS of the row before End Date + 30 days and
        number of rows with Processing or Proposed status in the ID less than the number of Visits
        """
        self._claim_result = self._sondermind_website.check_claim_entries()

    @step(5, 4)
    def get_client_email_optum(self):
        # TODO paste client email element's id
        # client_email = self._sondermind_website.browser.find_element("//input[@id='']").get_attribute("value")
        client_email = ""
        return client_email

    @step(5, 5)
    def check_insurance_rows_optum(self):
        """ """
        self._sondermind_website.browser.wait_until_element_is_visible("//table[@class='table table-striped']")

        insurance_row_xpath = "//tr[@class='insurance-card ']"
        insurance_rows = self._sondermind_website.browser.find_elements(insurance_row_xpath)
        processed_eap = False
        for index in range(len(insurance_rows)):
            processed_eap = False
            insurance_title = self._sondermind_website.browser.find_element(
                f"{insurance_row_xpath}[{index + 1}]/td[1]/span[1]"
            ).text
            if "EAP" in insurance_title:
                if not self._sondermind_website.browser.is_element_visible(  # contains DELETED
                    f"{insurance_row_xpath}[{index + 1}]/td[1]/span[@class='badge badge-warn']"
                ):
                    log.info("Found the EAP insurance")
                    client_name_sondermind = self._sondermind_website.browser.find_element(
                        "//ol[@class='breadcrumb']/li[2]/a"
                    ).text
                    self._sondermind_website.browser.click_element_when_visible("//a[text()='Edit']")
                    self.check_authorization_number_optum(client_name_sondermind)
                    processed_eap = True
        if not processed_eap:
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._sondermind_website.exit_record()

    @step(5, 6)
    def check_authorization_number_optum(self, client_name_sondermind):
        self._sondermind_website.browser.wait_until_element_is_visible("//input[@id='insurance_auth_number']")
        auth_number = self._sondermind_website.browser.find_element(
            "//input[@id='insurance_auth_number']"
        ).get_attribute("value")

        if auth_number:
            log.info(f"Found the auth_number {auth_number}\n")
            if self._sondermind_website.is_auth_number_optum_valid(auth_number):
                optum_website = Optum(CREDENTIALS["optum"], CREDENTIALS["gmail"])
                optum_website.login()
                optum_website.go_to_authorization_number_search_tab()
                optum_website.search_by_auth_number(auth_number)

                if optum_website.is_search_result():
                    client_name_optum = optum_website.get_optum_client_details()

                    if client_name_optum.lower() == client_name_sondermind.lower():
                        optum_website.go_to_inqury_details()
                        optum_client_details: dict = optum_website.get_optum_client_details()
                        self._sondermind_website.update_edit_insurance_window_with_optum_client_details(
                            optum_client_details
                        )
                        self._sondermind_website.close_current_window_and_switch_to_main()
                        self._sondermind_website.verify_opened_record()
                        self._report_item.verified_mark_as_worked = True
                        return
                    else:
                        log.info(
                            f"Client name from optum {client_name_optum} is not equal to "
                            f"client name from sonder mind {client_name_sondermind}"
                        )
                else:
                    log.info(f"No account with auth number {auth_number} was found")
            else:
                log.info(f"Auth_number {auth_number} is invalid")

            # if authorization number is not valid or no search result at optum site or clients name are not the same
            log.info("Making note and setting up client for cash pay...")
            self._sondermind_website.browser.click_element_when_visible(
                "//span[text()=' ×']/parent::button[@class='close']"
            )
            self._sondermind_website.go_to_client_note_tab_and_add_note("Invalid EAP Authorization number")
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._sondermind_website.set_up_client_for_cash_pay_and_submit_record()
            self._report_item.set_for_cash_pay = True
        else:
            log.info("No auth number was found, verifying the record")
            self._sondermind_website.close_current_window_and_switch_to_main()
            self._sondermind_website.verify_opened_record()
            self._report_item.verified_mark_as_worked = True

    @step(6)
    def send_report(self):
        if CONFIG.RUN_MODE == "PRD":
            gmail = GoogleMail()
            gmail.send_mail(CONFIG.CLIENT_MAILS, self._report.to_html("report_template.html"), "SM1 Report.")
