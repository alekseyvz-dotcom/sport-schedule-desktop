FROM python:3.11-slim

WORKDIR /app

# Зависимости для psycopg2 + Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc libjpeg-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt Pillow

# Код проекта
COPY . .

# Генерируем apple-touch-icon с тёмным фоном
RUN python3 -c "\
from PIL import Image;\
bg = Image.new('RGBA', (180, 180), (15, 23, 42, 255));\
logo = Image.open('assets/logo.png').convert('RGBA');\
logo.thumbnail((130, 130), Image.LANCZOS);\
x = (180 - logo.width) // 2;\
y = (180 - logo.height) // 2;\
bg.paste(logo, (x, y), logo);\
bg.convert('RGB').save('web/static/apple-touch-icon.png');\
print('apple-touch-icon created')"

EXPOSE 8000

CMD ["uvicorn", "web.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]
