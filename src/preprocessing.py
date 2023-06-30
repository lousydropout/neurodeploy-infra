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
        exec(preprocessing, globals())
    except Exception as err:
        logger.exception(err)
        return {"error": err}

    try:
        response = preprocess(payload)
        result = {"output": response}
    except Exception as err:
        logger.exception(err)
        result = {"error": err}

    logger.info("result: %s", json.dumps(result))
    return result
