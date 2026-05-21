FROM python:3.11-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /workspace

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      git \
      lmodern \
      texlive-fonts-extra \
      texlive-fonts-recommended \
      texlive-latex-base \
      texlive-latex-extra \
      texlive-latex-recommended \
      texlive-pictures && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt && \
    python -m playwright install --with-deps chromium && \
    chmod -R a+rX /ms-playwright

COPY pyproject.toml README.md /workspace/
COPY scripts /workspace/scripts
RUN python -m pip install --no-cache-dir --no-deps .

CMD ["job-hunter", "--help"]
