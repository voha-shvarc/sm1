# from gmail_api_connection import Create_Service
from libraries.google.gmail_connection import Create_Service
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from libraries import CREDENTIALS


class GoogleMail:
    def __init__(self):
        self.CLIENT_SECRET_FILE = CREDENTIALS["gmail"]["client_creds"]
        self.API_NAME = "gmail"
        self.API_VERSION = "v1"
        self.SCOPES = ["https://mail.google.com/"]
        self.TOKEN_FILE = CREDENTIALS["gmail"]["token"]

        self.service = Create_Service(
            self.CLIENT_SECRET_FILE, self.API_NAME, self.API_VERSION, self.TOKEN_FILE, self.SCOPES
        )

    def send_mail(self, recipients: list, message: str, subject: str):
        emailMsg = message
        mimeMessage = MIMEMultipart()
        mimeMessage["to"] = ", ".join(recipients)
        mimeMessage["subject"] = subject
        mimeMessage.attach(MIMEText(emailMsg, "html"))
        raw_string = base64.urlsafe_b64encode(mimeMessage.as_bytes()).decode()

        message = self.service.users().messages().send(userId="me", body={"raw": raw_string}).execute()
