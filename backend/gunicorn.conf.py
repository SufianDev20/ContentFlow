# Generation runs synchronously inside the request (see apps/jobs/views.py),
# so a multi-format job can take longer than gunicorn's 30 s default.
# Remove this once generation moves to a background task queue.
timeout = 120
