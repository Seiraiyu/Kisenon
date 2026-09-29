# CPU-only MinerU 3.4.5 (pipeline backend). Used once to build corpus/parsed/.
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
      "mineru[pipeline]==3.4.5" six
ENV MINERU_MODEL_SOURCE=huggingface
ENTRYPOINT ["mineru"]
