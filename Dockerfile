FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg tesseract-ocr libtesseract-dev \
    libnss3 libxss1 libasound2 libxtst6 libgbm1 \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set environment variables
ENV PORT=8000
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Explicitly expose the port
EXPOSE $PORT

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]