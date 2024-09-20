###################################
#
#   Dockerfile for Discord Bot
#
#   Author: Thorsten Liepert
###################################
FROM python:3.12-alpine

RUN mkdir /app

ADD requirements.txt /app
ADD main.py /app
ADD modules/ /app/modules

RUN addgroup -S bot -g 1000 && \
    adduser -S bot -G bot -u 1000 && \
    chown -R 1000:1000 /app

WORKDIR /app

RUN python -m pip install -r requirements.txt 

USER bot
ENV PYTHONPATH=/app
CMD ["python", "-u", "./main.py"]
