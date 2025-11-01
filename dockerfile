FROM python:3.13-slim

WORKDIR /app

# Copy and install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
