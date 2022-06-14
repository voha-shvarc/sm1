import os
import ssl
from typing import List
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httplib2
from retry import retry
from libraries import CONFIG, logger as log


class GoogleSheets:
    def __init__(self, sheet_id: str):
        self.sheet_id = sheet_id
        self.http, self.service = self._init_service()
        self.clients: List[list] = []

    @staticmethod
    def _get_credentials() -> ServiceAccountCredentials:
        """Get the Google Drive API credentials."""
        service_account_path = os.path.join(CONFIG.PATHS.TEMP, "sondermind_service_account.json")
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            service_account_path, scopes="https://www.googleapis.com/auth/spreadsheets"
        )
        return credentials

    def _init_service(self) -> (httplib2.Http, build):
        """Create an authorized Spreadsheets API service instance."""
        log.info("Initializing Google Sheets service...")
        credentials = self._get_credentials()
        http = httplib2.Http()
        http = credentials.authorize(http)
        return http, build("sheets", "v4", http=http)

    def add_client_info(self, first_name, last_name, date_of_birth, auth_num):
        self.clients.append([first_name, last_name, date_of_birth, auth_num])

    def send_clients_info_to_sheet(self):
        if not self.clients:
            log.info("GOOGLE SHEETS: No clients with valid authorization number was found, nothing to send")
            return

        first_last_name_dob_sheet_body = {"values": [client[:-1] for client in self.clients]}
        f_l_dob_range = "Sondermind EAP Authorizations!A1:C1"  # first name, lat name, date of birth range
        authorization_number_sheet_body = {"values": [client[-1] for client in self.clients]}
        auth_num_range = "Sondermind EAP Authorizations!G1"

        log.info("GOOGLE SHEETS: Sending clients info to Google Sheets...")
        self._post_client_info_to_sheet(f_l_dob_range, first_last_name_dob_sheet_body)
        self._post_client_info_to_sheet(authorization_number_sheet_body, auth_num_range)

    @retry((TimeoutError, ssl.SSLEOFError, HttpError, BrokenPipeError), tries=4, delay=5, backoff=2)
    def _post_client_info_to_sheet(self, sheet_range, sheet_body):
        # self.clients = [["vova", "sheva", "1234", 2], ["senya", "kek", "25324" , 3]]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id, range=sheet_range, body=sheet_body, valueInputOption="USER_ENTERED"
        ).execute()
