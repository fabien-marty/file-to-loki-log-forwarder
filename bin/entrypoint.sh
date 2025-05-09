#!/bin/sh

cd /app || exit 1
. .venv/bin/activate

exec python bin/main.py
