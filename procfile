web: python manage.py collectstatic --noinput && gunicorn creative_match.wsgi:application --bind :$PORT --workers 2 --threads 8 --timeout 0
