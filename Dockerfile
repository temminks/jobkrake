FROM python:3.8-slim

RUN apt-get update && apt-get -y upgrade

RUN pip install --upgrade pip

RUN pip install quart aiohttp requests bs4 PyYAML

COPY app /app/

WORKDIR /app

CMD ["hypercorn", "--bind", "0.0.0.0:9000", "app:app"]