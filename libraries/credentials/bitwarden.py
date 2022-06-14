import os
from pathlib import Path
from RPA.Robocorp.Vault import Vault
from ta_bitwarden_cli.ta_bitwarden_cli import Bitwarden

from libraries import CONFIG, logger


def get_attachment(cred_group, attachment_name, output_dir="None"):
    output_dir = output_dir if Path(output_dir).exists() else CONFIG.PATHS.TEMP
    bit_warden.get_attachment(cred_group, attachment_name, str(output_dir))


logger.info("requesting credentials...")
if CONFIG.RUN_MODE == "DEV":
    logger.info("TEST RUN")
    bitwarden_credentials = {
        "username": os.environ["USERNAME"],
        "client_id": os.environ["CLIENT_ID"],
        "client_secret": os.environ["CLIENT_SECRET"],
        "password": os.environ["PASSWORD"],
    }
else:
    bitwarden_credentials = Vault().get_secret("bitwarden_credentials")
bit_warden = Bitwarden(bitwarden_credentials)
bit_warden.bitwarden_login()

_request_credentials = {
    "gmail": "Gmail Account",
    "sondermind": "SonderMind",
    "optum": "One Healthcare ID (Optum)",
    "captcha": "Captcha Guru",
}
CREDENTIALS = bit_warden.get_credentials(_request_credentials)
creds_filename = "client_creds.json"
bit_warden.get_attachment(_request_credentials["gmail"], creds_filename, str(CONFIG.PATHS.TEMP))
CREDENTIALS["gmail"]["client_creds"] = str(Path(CONFIG.PATHS.TEMP) / creds_filename)
token_filename = "token"
bit_warden.get_attachment(_request_credentials["gmail"], token_filename, str(CONFIG.PATHS.TEMP))
CREDENTIALS["gmail"]["token"] = str(Path(CONFIG.PATHS.TEMP) / token_filename)

get_attachment("Gmail Account", "sondermind_service_account.json")  # service account for working with Google Sheets API
