from helpers import cors


def handler(event: dict, context) -> dict:
    return cors.get_response(
        status_code=204,
        methods="POST",
        additional_headers="Content-Type, username, password",
    )
