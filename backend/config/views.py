from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Liveness probe: checks the database only, never third-party providers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": "error"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})
