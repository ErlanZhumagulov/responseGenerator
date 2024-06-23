# Используем базовый образ Python
FROM python

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем зависимости (файл requirements.txt) в контейнер
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все содержимое текущей директории в контейнер в папку /app
COPY . .

# Указываем команду, которая будет запускать приложение
CMD ["python", "app.py"]
