# Используем официальный образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
# RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код проекта
COPY . .

# Команда для запуска бота
CMD ["python", "main.py"]
