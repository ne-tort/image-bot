FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ core/
COPY tgbot/ tgbot/
COPY app/ app/

ENV DB_PATH=/data/imagebot.db
VOLUME /data

# непривилегированный пользователь — и volume читается, и в контейнере чисто
RUN useradd -m -u 1000 bot && mkdir -p /data && chown -R bot:bot /data /app
USER bot

CMD ["python", "-m", "app.main"]
