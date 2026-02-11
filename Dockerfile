# Python 3.11 slim — меньше размер образа
FROM python:3.11-slim

WORKDIR /app

# Сначала зависимости — слой кэшируется при неизменном requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY main.py .
COPY content/ content/
COPY storage/ storage/

# Бот с long polling (не веб-сервер)
CMD ["python", "main.py"]
