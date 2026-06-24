FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" easy

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt

COPY . /app
RUN python manage.py collectstatic --noinput && chown -R easy:easy /app

USER easy
EXPOSE 8000

CMD ["gunicorn", "easy_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
