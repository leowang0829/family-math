FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 math \
    && useradd --uid 10001 --gid math --no-create-home math \
    && mkdir /data && chown math:math /data
COPY --chown=math:math run.py ./
COPY --chown=math:math app ./app
USER math
ENV MATH_BIND=0.0.0.0 MATH_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8921
CMD ["python", "run.py"]
