# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt requests
COPY app.py .
COPY <<'ADAPTER' /app/provider_adapter.txt
# Isolated experimental provider adapter. No account cookies or API keys.
import json, subprocess
from urllib.parse import urlsplit, parse_qs

_native_download = run_download
_provider_lock = threading.Lock()
_provider_last = [0.0]

def run_download(jid, url, mode, outdir):
    host = (urlsplit(url).hostname or '').lower()
    youtube = host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be')
    if not youtube:
        return _native_download(jid, url, mode, outdir)
    job = JOBS[jid]
    try:
        if os.environ.get('DG_YOUTUBE_PROVIDER', 'gendownload') != 'gendownload':
            raise RuntimeError('YouTube provider is disabled.')
        if mode not in ('audio', 'video'):
            raise RuntimeError('Choose video or audio.')
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None,443):
            raise RuntimeError('Use a normal HTTPS YouTube link.')
        if host == 'youtu.be':
            vid = parts.path.strip('/').split('/')[0]
        elif parts.path == '/watch':
            vid = parse_qs(parts.query).get('v',[''])[0]
        elif parts.path.startswith(('/shorts/', '/embed/', '/live/')):
            vid = parts.path.strip('/').split('/')[1]
        else:
            vid = ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise RuntimeError('Paste a single public YouTube video link, not a playlist.')
        with _provider_lock:
            if time.monotonic()-_provider_last[0] < 8:
                raise RuntimeError('Wait a few seconds before another YouTube request.')
            _provider_last[0] = time.monotonic()
        import requests
        r = requests.post('https://gendownload.com/api/extract',json={'url':'https://www.youtube.com/watch?v='+vid},timeout=(10,75))
        r.raise_for_status()
        data = r.json()
        formats = data.get('formats') or []
        videos = [x for x in formats if x.get('type')=='video']
        fmt = next((x for x in videos if x.get('label')=='360p'),None) or next((x for x in videos if x.get('label')=='720p'),None)
        if not fmt:
            raise RuntimeError('Provider returned no supported format. Try later.')
        stream = fmt.get('url','')
        p = urlsplit(stream)
        if p.scheme != 'https' or p.hostname not in ('dl.gendownload.com','gendownload.com') or p.username or p.password or p.port not in (None,443) or p.path != '/api/stream':
            raise RuntimeError('Provider returned an unexpected stream address.')
        target = os.path.join(outdir,'source.bin')
        deadline = time.monotonic()+210
        size = 0
        with requests.get(stream,stream=True,allow_redirects=False,timeout=(10,45)) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise RuntimeError('Provider stream was not available.')
            with open(target,'wb') as f:
                for chunk in response.iter_content(262144):
                    if time.monotonic()>deadline:
                        raise RuntimeError('Provider download timed out. Try later.')
                    size += len(chunk)
                    if size > 150*1024*1024:
                        raise RuntimeError('Experimental YouTube downloads are limited to 150 MB.')
                    f.write(chunk)
                    job['progress'] = min(90,5+size//1048576)
        if size < 1024:
            raise RuntimeError('Provider returned an empty file.')
        probe = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',target],capture_output=True,text=True,timeout=15,check=True)
        meta = json.loads(probe.stdout)
        types = {s.get('codec_type') for s in meta.get('streams',[])}
        if 'audio' not in types or (mode=='video' and 'video' not in types):
            raise RuntimeError('Provider returned missing audio or video; file rejected.')
        expected = float(data.get('duration') or 0)
        actual = float(meta.get('format',{}).get('duration') or 0)
        if expected and actual < expected-5:
            raise RuntimeError('Provider returned an incomplete file; file rejected.')
        title = re.sub(r'[^A-Za-z0-9._ -]','_',str(data.get('title') or 'YouTube video'))[:80]
        filename = title + ('.mp3' if mode=='audio' else '.mp4')
        output = os.path.join(outdir,filename)
        args = ['ffmpeg','-v','error','-i',target]
        args += ['-vn','-codec:a','libmp3lame','-b:a','192k'] if mode=='audio' else ['-map','0:v:0','-map','0:a:0','-c','copy','-movflags','+faststart']
        job['progress'] = 100
        subprocess.run(args+['-y',output],capture_output=True,timeout=300,check=True)
        os.remove(target)
        job.update(status='done',progress=100,title=data.get('title'),filename=filename)
    except Exception as exc:
        shutil.rmtree(outdir,ignore_errors=True)
        if isinstance(exc,RuntimeError):
            msg = str(exc)
        else:
            msg = 'YouTube provider failed or timed out. No file was saved. Try later.'
        job.update(status='error',error=msg[:220])
ADAPTER
RUN python - <<'PY'
p='app.py'
s=open(p).read()
s=s.replace('if __name__ == "__main__":',open('provider_adapter.txt').read()+'\nif __name__ == "__main__":')
compile(s,p,'exec')
open(p,'w').write(s)
PY
ENV PORT=8000
EXPOSE 8000
CMD ["gunicorn", "-w", "1", "--threads", "8", "-t", "0", "-b", "0.0.0.0:10000", "app:app"]
