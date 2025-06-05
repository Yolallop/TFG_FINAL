#!/bin/sh
export PORT=${PORT:-8000}
gunicorn app:app --bind=0.0.0.0:$PORT --timeout 900
