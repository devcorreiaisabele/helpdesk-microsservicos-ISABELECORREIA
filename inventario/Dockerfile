FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Usuário sem privilégios (uid 10001) e diretório de dados gravável por ele.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /dados /srv \
    && chown 10001:10001 /dados

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=10001:10001 app ./app

USER 10001:10001

ENV DATABASE_URL=sqlite:////dados/inventario.db
VOLUME ["/dados"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
