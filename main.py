from libraries import logger
from sm1_benefits_verification import Sm1BenefitsVerification
from supervisor.dynamic import supervise


def main():
    """Main function which calls all other functions."""
    logger.info("Initiating Robot Workflow Test")
    with supervise(manifest="manifest.yaml", output_dir="output"):
        dw = Sm1BenefitsVerification()
        dw.login_to_sondermind()
        # dw.go_to_benefits_verification()
        # dw.start_insurance_loop()


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logger.exception("Exception in main function %s" % ex)
