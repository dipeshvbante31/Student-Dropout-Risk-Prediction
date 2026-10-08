web: FLASK_APP=wsgi flask db upgrade && gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
