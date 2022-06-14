import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path


class RUNMODES:
    DEV = "DEV"
    PRD = "PRD"


class CONFIG:
    if len(sys.argv) > 1 and sys.argv[1].lower() == "local":
        RUN_MODE = RUNMODES.DEV
    else:
        RUN_MODE = RUNMODES.PRD

    class PATHS:
        DW = Path().parent.parent.resolve()
        TEMP = Path(TemporaryDirectory().name)
        BOT = os.getcwd()

    BENEFIT_VERIFICATION_URL = (
        "https://admin.sondermind.com/"
        "super_bill_management/benefit_verifications/failed_entry#/failed-insurance-verification"
    )
    INSURANCE_LIST = ["Cigna", "United Health Care"]

    CLIENT_MAILS = ["bhardy@sondermind.com", "jwebb@sondermind.com", "kortega@sondermind.com"]
