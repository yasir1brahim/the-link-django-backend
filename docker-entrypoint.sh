#!/bin/bash

python manage.py migrate
python manage.py collectstatic --noinput
gunicorn the_link.wsgi -t 900 -b 0.0.0.0:8000 --workers 3
