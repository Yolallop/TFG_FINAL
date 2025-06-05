# Usa una imagen de base con Python
FROM python:3.10-slim

# Instala dependencias del sistema
RUN apt-get update && apt-get install -y ffmpeg build-essential libpq-dev gcc

# Crea el directorio de la app
WORKDIR /app

# Copia el contenido
COPY . .

# Instala las dependencias de Python
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expone el puerto (el que usa Azure internamente)
EXPOSE 8000

# Comando de inicio
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--timeout", "900"]
