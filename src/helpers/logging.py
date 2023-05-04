import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

log_format = "[%(levelname)s] %(filename)s:%(lineno)d:%(funcName)s: %(message)s"
date_format = "%Y-%m-%dT%H:%M:%S"

# Configure the logger to use the new format
formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
for handler in logger.handlers:
    handler.setFormatter(formatter)
    logger.addHandler(handler)


logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
