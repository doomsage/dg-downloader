# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*
RUN curl -fL --retry 2 https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_linux_amd64 -o /usr/local/bin/wgcf && chmod 755 /usr/local/bin/wgcf \
 && curl -fL --retry 2 https://github.com/windtf/wireproxy/releases/download/v1.1.3/wireproxy_linux_amd64.tar.gz -o /tmp/wireproxy.tar.gz \
 && tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin wireproxy && chmod 755 /usr/local/bin/wireproxy \
 && curl -fL --retry 2 https://github.com/denoland/deno/releases/download/v2.9.8/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
 && unzip /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip /tmp/wireproxy.tar.gz
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 'yt-dlp[default]'
COPY app.py .
RUN python - <<'PY'
p='app.py'
s=open(p).read()
needle='    if mode == "audio":\n        opts["format"]'
replacement='''    from urllib.parse import urlparse
    hostname = (urlparse(url).hostname or "").lower()
    if hostname in ("youtube.com", "youtu.be") or hostname.endswith(".youtube.com"):
        opts["proxy"] = "socks5://127.0.0.1:1080"
        opts["source_address"] = "0.0.0.0"
        opts["format"] = "140/bestaudio" if mode == "audio" else "18/b[height<=360]"
        opts["js_runtimes"] = {"deno": {"path": "/usr/local/bin/deno"}}
    if mode == "audio":
        opts["format"]'''
assert needle in s
s=s.replace(needle,replacement,1)
needle2='    try:\n        with yt_dlp.YoutubeDL(opts) as y:'
replace2='    if hostname in ("youtube.com", "youtu.be") or hostname.endswith(".youtube.com"):\n        opts["format"] = "140/bestaudio" if mode == "audio" else "18/b[height<=360]"\n    try:\n        with yt_dlp.YoutubeDL(opts) as y:'
assert needle2 in s
open(p,'w').write(s.replace(needle2,replace2,1))
PY
COPY <<'SH' /app/start.sh
#!/bin/sh
set -eu
mkdir -p /tmp/warp
cd /tmp/warp
if timeout 30 wgcf register --accept-tos > /tmp/warp-register.log 2>&1 && wgcf generate > /tmp/warp-generate.log 2>&1; then
    sed -i 's/AllowedIPs = .*/AllowedIPs = 0.0.0.0\/0/' wgcf-profile.conf
    printf '\n[Socks5]\nBindAddress = 127.0.0.1:1080\n' >> wgcf-profile.conf
    wireproxy -c wgcf-profile.conf > /tmp/warp-proxy.log 2>&1 &
    echo 'WARP proxy started (YouTube only)'
else
    echo 'WARP registration failed; non-YouTube downloads remain available'
fi
cd /app
exec gunicorn -w 1 --threads 8 -t 0 -b "0.0.0.0:${PORT:-8000}" app:app
SH
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "/app/start.sh"]
