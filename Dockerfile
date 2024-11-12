###################################
#
#   Dockerfile for Discord Bot
#
#   Author: Thorsten Liepert
###################################
FROM python:3.12-alpine AS build
RUN mkdir -p /app/locale/de/LC_MESSAGES

COPY locale/de/LC_MESSAGES/messages.po /app/locale/de/LC_MESSAGES

RUN apk add --update --no-cache icu-dev gettext gettext-dev

WORKDIR /app/locale/de/LC_MESSAGES
RUN msgfmt messages.po

FROM python:3.12-alpine

RUN apk add --update --no-cache gettext && \
    mkdir -p /app/locale

COPY requirements.txt main.py /app/
COPY modules/ /app/modules
COPY --from=build /app/locale/ /app/locale

WORKDIR /app

RUN python -m pip install --no-cache-dir -r requirements.txt 

ENV PYTHONPATH=/app
CMD ["python", "-u", "./main.py"]
