# -------------------
# The build container
# -------------------
FROM python:3.8-slim-bookworm AS build 

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
    build-essential \
    unzip && \
  rm -rf /var/lib/apt/lists/*

COPY . /root

RUN python -m pip install --upgrade pip && \
  pip install --no-cache-dir "setuptools==69.5.1" "wheel" "Cython<3.0" && \
  cd /root && \
  sed -i '/gevent/d' requirements.txt && \
  echo "gevent==21.12.0" >> requirements.txt && \
  pip install --no-cache-dir --no-warn-script-location --ignore-installed -r requirements.txt && \
  python setup.py build_ext --inplace


# -------------------------
# The application container
# -------------------------
FROM python:3.8-slim-bookworm

EXPOSE 8000/tcp

RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    imagemagick \
    tini && \
  rm -rf /var/lib/apt/lists/*


COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /root /root

RUN rm /etc/ImageMagick-6/policy.xml && \
  mkdir -p /run/tawhiri

WORKDIR /root

ENV PATH=/usr/local/bin:$PATH

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "12", "tawhiri.api:app"]
