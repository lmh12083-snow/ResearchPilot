# ResearchPilot backend image.
# Build context must be ./backend (see root docker-compose.yml).
FROM python:3.12-slim

# System deps: libgomp1 is required by the CPU torch wheel (OpenMP runtime).
# curl is handy for debugging inside the container.
# deb.debian.org is unreliable/blocked in CN networks — use the Tsinghua mirror.
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch FIRST so pip does NOT pull the multi-GB CUDA build
# when sentence-transformers resolves its torch dependency. Version matches
# the stack verified on the dev machine (py -3.10, torch 2.13.0+cpu).
# download.pytorch.org is slow/blocked in CN — install the exact CPU wheel
# from the Aliyun mirror; its deps resolve from the Tsinghua PyPI mirror.
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"

COPY requirements.txt .
# pypi.org is unreliable in CN — use the Tsinghua PyPI mirror.
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Embedding + reranker models are supplied at runtime by mounting the host
# HuggingFace cache into /root/.cache/huggingface (see docker-compose.yml).
# HF_HUB_OFFLINE=1 makes loading read only the cache — huggingface.co is
# blocked in CN and hf-mirror.com 308-redirects model files back to it, so
# downloading at build/run time is unreliable. The image stays lean this way.

# App code last — the earlier layers stay cached across code edits.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
