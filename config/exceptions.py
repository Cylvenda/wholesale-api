from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    return Response(
        {"success": False, "data": response.data},
        status=response.status_code,
        headers=response.headers,
    )


from rest_framework.response import Response
