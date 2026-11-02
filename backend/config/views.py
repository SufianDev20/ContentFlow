from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse


def index(request):
    return render(request, "index.html")


def login(request):
    return render(request, "login.html")


def register(request):
    return render(request, "register.html")


def logout(request):
    # For JWT authentication, the client handles token clearing
    # Just redirect to login page
    return redirect("login")


def dashboard(request):
    return render(request, "dashboard.html")


def settings(request):
    return render(request, "dashboard.html")


def history(request):
    return render(request, "history.html")


def job(request):
    return render(request, "job.html")


def stats(request):
    return render(request, "stats.html")


def health_check(request):
    """
    Liveness/readiness probe for infra (load balancers, uptime monitors).

    Checks DB connectivity only — deliberately does not call out to
    OpenRouter/Gemini, since that would make a cheap liveness probe slow
    and dependent on a third party's uptime.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": "error"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})
