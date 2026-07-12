FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 9400

ENTRYPOINT ["agentgate"]
CMD ["--config", "tools.yaml", "--host", "0.0.0.0"]
