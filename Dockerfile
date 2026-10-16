FROM python:3.11-slim

WORKDIR /app

# ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードのコピー
COPY src/ ./src/

# スクリプトの実行
CMD ["python", "-u", "src/main.py"]