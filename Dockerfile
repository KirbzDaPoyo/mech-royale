FROM python:3.13-slim
WORKDIR /bot
COPY python/*.py ./
ENTRYPOINT ["python3", "-u", "/bot/example_bot.py"]
