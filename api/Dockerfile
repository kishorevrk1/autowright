FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build context is ./api, so copy its contents into /app/api/
# so `uvicorn api.main:app` and `from api.xxx import` both resolve correctly.
COPY . ./api/

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
