###################################
#
#   Dockerfile for Discord Bot
#
#   Author: Thorsten Liepert
###################################
FROM python:3.12-alpine

RUN mkdir /app

COPY requirements.txt main.py /app/
COPY modules/ /app/modules

WORKDIR /app

RUN python -m pip install --no-cache-dir -r requirements.txt 

ENV PYTHONPATH=/app
CMD ["python", "-u", "./main.py"]
