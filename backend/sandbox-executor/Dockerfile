FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py /app/server.py
RUN pip install --no-cache-dir pandas openpyxl matplotlib pypdf python-docx python-pptx pillow \
    && useradd --create-home --uid 10001 sandbox
USER 10001
EXPOSE 3020
CMD ["python", "/app/server.py"]
