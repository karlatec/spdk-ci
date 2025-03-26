FROM python:3.12-alpine
RUN pip install requests
COPY artifact_manager.py /app/artifact_manager.py
CMD [ "python", "-u", "/app/artifact_manager.py"]
