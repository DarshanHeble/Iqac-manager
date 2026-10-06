# =============================================================================
# Backend image — Flask + gunicorn
#
# Layout note: the code lives at /app/backend and gunicorn is started with
# `--chdir backend`, matching backend/Procfile. That is not arbitrary — the Flask
# app resolves templates, static files and the logo relative to app.py, and
# several modules use flat imports (`from db import …`), so `backend/` has to be
# the working directory for imports to resolve.
# =============================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libfreetype6 for ReportLab's bundled Type1 fonts, libjpeg for its image
# support. Nothing here needs a TTF package: the PDF code asks for
# 'Times-Roman' and friends, which ReportLab ships.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libfreetype6 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so a source-only change does not reinstall the world.
COPY requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY . ./backend/

# app.py creates these on import and uploads land in them, so they must exist and
# be writable before the first request.
RUN mkdir -p backend/static/signed_reports backend/static/attachments

EXPOSE 5000

# --workers 1 is deliberate, not a default.
#
# app.py calls scheduler.start() at module import. Every gunicorn worker imports
# the app, so N workers means the 18:00 IST reminder job fires N times and every
# coordinator gets N emails. Scale with --threads (gunicorn is threaded, not
# forked-per-request here) rather than with workers until the scheduler is moved
# out of import.
#
# Also: gunicorn must not use --preload, which would run the import once in the
# master and share the scheduler across workers — that would look like a fix for
# the wrong problem and would still leave one job per worker process.
CMD ["gunicorn", \
     "--chdir", "backend", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]