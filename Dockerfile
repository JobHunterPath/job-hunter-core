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
    curl -fsSL -o /usr/local/bin/lightpanda \
      https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux && \
    chmod 0755 /usr/local/bin/lightpanda && \
    chmod -R a+rX /ms-playwright

COPY pyproject.toml /workspace/
COPY src /workspace/src
RUN python -m pip install --no-cache-dir --no-deps .

CMD ["job-hunter", "--help"]
