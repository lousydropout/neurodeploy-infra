from helpers import cors


def handler(event: dict, context) -> dict:
    return cors.get_response(
        status_code=204,
        methods="GET, DELETE, POST",
        additional_headers="credentials_name, description",
    )
