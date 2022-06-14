"""
Authenticates with an AWS CodeArtifact index, installs packages, and
runs a subcommand. This is intended to be used as a DW entrypoint.

usage: codeartifact_shim.py [-h] [--secret SECRET] [--requirements REQUIREMENTS]
                            [--command COMMAND [COMMAND ...]]

Test for argparse

optional arguments:
  -h, --help            show this help message and exit
  --secret SECRET       The name of the vault secret that contains the AWS
                        credentials
  --requirements REQUIREMENTS
                        The requirements file with packages to install
                        from CodeArtifact
  --command COMMAND [COMMAND ...]
                        The subcommand to run after installing packages
                        from CodeArtifact

Examples
========

# Use the Robocorp Vault secret named "aws_creds" to auth with CodeArtifact,
# download packages listed in "requirements.txt", then run "python3 main.py"
# as a subprocess.
python3 codeartifact_shim.py \
    --secret aws_creds \
    --requirements requirements.txt \
    --command python3 main.py \
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List

import boto3
from RPA.Robocorp.Vault import Vault

logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(console_handler)


def new_boto_session(role_arn: str, external_id: str, region: str) -> boto3.Session:
    """
    Creates a new boto3 session by assuming a given role using an external ID.

    Args:
        role_arn (str): The role to assume.
        external_id (str): The external ID to use when assuming the role.
        region (str): The AWS region to use.

    Returns:
        boto3.Session: The authenticated session.
    """

    # Grab credentials via STS assume-role
    logger.info("Creating new AWS boto3 session from role %s", role_arn)
    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="thoughtful-codeartifact",
        ExternalId=external_id,
    )

    # Create a new session
    return boto3.Session(
        aws_access_key_id=response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
        aws_session_token=response["Credentials"]["SessionToken"],
        region_name=region,
    )


@dataclass
class AWSConfiguration:
    """
    A data class that represents the configuration for an AWS CodeArtifact repo.

    Attributes:
        role_arn (str): The role to assume.
        external_id (str): The external ID to use when assuming the role.
        region (str): The AWS region to use.
        domain (str): The AWS CodeArtifact domain to use.
        domain_owner (str): The AWS CodeArtifact domain owner of the repo.
    """

    role_arn: str
    external_id: str
    region: str
    domain: str
    domain_owner: str

    @classmethod
    def from_vault(cls, vault: Vault, secret_name: str) -> AWSConfiguration:
        """
        Create a new instance of this class from a Robocorp Vault secret.

        Args:
            vault (Vault): The vault to read secret values from.
            secret_name (str): The name of the secret that has the AWS configuration
            values.

        Returns:
            AWSConfiguration: The credentials read from the vault.
        """

        vault_keys = ["role_arn", "external_id", "region", "domain", "domain_owner"]
        logger.info("Using vault secret %s and keys %s", secret_name, vault_keys)
        vault_secret = vault.get_secret(secret_name)
        init_kwargs: Dict[str, str] = {k: vault_secret[k] for k in vault_keys}

        return cls(**init_kwargs)


class CodeArtifact:
    def __init__(self, session: boto3.Session, domain: str, domain_owner: str) -> None:
        """
        A wrapper around the AWS CodeArtifact API (part of the `boto3` library).

        Args:
            session (boto3.Session): The session to use for AWS CodeArtifact API calls.
            domain (str): The AWS CodeArtifact domain to use.
            domain_owner (str): The AWS CodeArtifact domain owner of the repo.

        Attributes:
            session (boto3.Session): The session to use for AWS CodeArtifact API calls.
            aws_ca (boto3.Client): The AWS CodeArtifact client.
            domain (str): The AWS CodeArtifact domain to use.
            domain_owner (str): The AWS CodeArtifact domain owner of the repo.
            authorization_token (str): The authorization token to use for AWS CodeArtifact API calls.
        """

        self.session = session
        self.aws_ca = self.session.client("codeartifact")

        self.domain = domain
        self.domain_owner = domain_owner

        token_response = self.aws_ca.get_authorization_token(domain=self.domain, domainOwner=self.domain_owner)
        self.authorization_token: str = token_response["authorizationToken"]

    @property
    def index_url(self) -> str:
        """
        The URL of the AWS CodeArtifact index. This index URL can be used for commands
        like `pip3 install -i <index_url> -r requirements.txt`. This URL includes the
        username (`aws`) and password (an authorization token) before the hostname.

        Returns:
            str: The URL.
        """
        user = "aws"
        password = self.authorization_token
        url = f"{self.domain}-{self.domain_owner}.d.codeartifact.us-east-1.amazonaws.com/pypi/{self.domain}/simple/"
        return f"https://{user}:{password}@{url}"

    def install(self, requirements_file: str) -> None:
        """
        Installs packages from a file such as `requirements.txt` by calling
        out to an AWS CodeArtifact index.

        Args:
            requirements_file (str): The name of the file to read packages from.
        """
        args = [
            "python",
            "-m",
            "pip",
            "install",
            "--index-url",
            self.index_url,
            "-r",
            requirements_file,
        ]
        logger.info("Installing requirements from %s", requirements_file)
        logger.info("With command: %s", args)
        subprocess.check_call(args)

    def __str__(self) -> str:
        return "{}(session={}, domain={}, domain_owner={}, authorization_token={})".format(
            self.__class__.__name__,
            self.session,
            self.domain,
            self.domain_owner,
            self.authorization_token[:10],
        )

    def __repr__(self) -> str:
        return "{}(session={}, domain={}, domain_owner={})".format(
            self.__class__.__name__,
            self.session,
            self.domain,
            self.domain_owner,
        )


@dataclass
class CommandLineArguments:
    """
    A data class that represents the command line arguments passed to this script.

    Attributes:
        secret (str): The name of the secret that has the AWS configuration values.
        requirements (str): The name of the file to read packages from.
        command (List[str]): The subcommand to run after downloading the requirements.
    """

    secret: str
    requirements: str
    command: List[str]

    @classmethod
    def from_argparse(cls, args: argparse.Namespace) -> CommandLineArguments:
        """
        Create a new instance of this class from the command line arguments.

        Args:
            args (argparse.Namespace): The arguments to parse.

        Returns:
            CommandLineArguments: The arguments.
        """

        return cls(secret=args.secret, requirements=args.requirements, command=args.command)


def main(args: CommandLineArguments) -> None:
    """

    The entry point for this script. Grabs the AWS configuration from the Vault,
    installs the requirements, and then runs the requested command as a
    subprocess.

    Args:
        args (CommandLineArguments): The command line arguments.
    """

    logger.info("Getting secrets from vault")
    robo_vault = Vault()
    creds = AWSConfiguration.from_vault(robo_vault, args.secret)

    logger.info("Connecting to CodeArtifact")
    session = new_boto_session(creds.role_arn, creds.external_id, creds.region)
    c = CodeArtifact(session, creds.domain, creds.domain_owner)

    logger.info("Installing requirements from %s", args.requirements)
    c.install(args.requirements)

    logger.info("Running subcommand: %s", args.command)
    subprocess.check_call(args.command, env=os.environ, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    # Set up CLI arguments
    parser = argparse.ArgumentParser(description="Test for argparse")
    parser.add_argument(
        "--secret",
        help="The name of the vault secret that contains the AWS credentials",
    )
    parser.add_argument(
        "--requirements",
        help="The requirements file with packages to install from CodeArtifact",
    )
    parser.add_argument(
        "--command",
        nargs="+",
        help="The subcommand to run after installing packages from CodeArtifact",
    )

    # Parse CLI args
    namespace = parser.parse_args()
    args = CommandLineArguments.from_argparse(namespace)
    logger.info("args: %s", args)

    # Run the script
    main(args)
