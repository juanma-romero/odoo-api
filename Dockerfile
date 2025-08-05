FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . /app

# Instala las dependencias
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" certifi python-dotenv pydantic

# Expón el puerto por defecto de Uvicorn
EXPOSE 8008

# Comando para arrancar el servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
