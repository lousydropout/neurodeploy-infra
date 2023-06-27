import json
from helpers.logging import logger
import numpy as np
import pandas as pd


def handler(event: dict, context) -> dict:
    logger.debug("Event: %s", json.dumps(event))

    preprocessing = event["preprocessing"]
    payload = event["payload"]

    # execute preprocessing source code to get
    # "preprocess" function
    try:
        exec(preprocessing)
    except Exception as err:
        logger.exception(err)
        return {"error": err}

    try:
        result = preprocess(payload)
    except Exception as err:
        logger.exception(err)
        result = {"error": err}

    return result
