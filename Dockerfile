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

WORKDIR /app

RUN python -m pip install -r requirements.txt 

ENV PYTHONPATH=/app
CMD ["python", "-u", "./main.py"]
