from unittest.mock import patch


def test_reports_ok_without_authentication(client, db):
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_reports_503_without_leaking_the_error_when_the_database_is_down(client):
    with patch("config.views.connection") as connection:
        connection.cursor.side_effect = Exception("connection refused: secret-host")
        response = client.get("/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error"}
