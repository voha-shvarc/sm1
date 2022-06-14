"""
Basic logging, centralized so sinks/other logging necessities can be customized centrally
"""
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
logger.info("logging instantiated")
logger.propagate = False
