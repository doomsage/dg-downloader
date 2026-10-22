import os, re, threading, time, uuid, shutil
from flask import Flask, request, jsonify, send_from_directory, render_template_string, abort

SECRET = os.environ.get("DG_SECRET")
if not SECRET or not re.fullmatch(r"[a-z0-9-]{8,64}", SECRET or ""):
    raise RuntimeError("Set DG_SECRET env var (8-64 chars of a-z 0-9 -). It is the private URL path.")
DOWNLOAD_DIR = "/tmp/dg-downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
JOBS = {}

def cleanup():
    while True:
        time.sleep(300)
        now = time.time()
        for jid, job in list(JOBS.items()):
            if now - job["created"] > 1800:
                shutil.rmtree(os.path.join(DOWNLOAD_DIR, jid), ignore_errors=True)
                JOBS.pop(jid, None)

threading.Thread(target=cleanup, daemon=True).start()

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Downloader</title>
<style>
  :root { --bg:#07070c; --card:#10101a; --line:#1e1e2e; --txt:#f2f2f7; --dim:#8a8a9e;
          --a1:#6366f1; --a2:#a855f7; --ok:#34d399; --err:#f87171; }
  * { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { background:var(--bg); color:var(--txt); font-family:-apple-system,'Segoe UI',Inter,Roboto,sans-serif;
         min-height:100vh; display:flex; flex-direction:column; align-items:center; padding:0 18px; }
  .glow { position:fixed; top:-180px; left:50%; transform:translateX(-50%); width:560px; height:360px;
          background:radial-gradient(ellipse, rgba(99,102,241,.28), transparent 65%); pointer-events:none; }
  main { width:100%; max-width:480px; margin-top:64px; position:relative; z-index:1; flex:1; }
  h1 { font-size:30px; font-weight:700; letter-spacing:-.5px;
       background:linear-gradient(90deg,#c7d2fe,#e9d5ff); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .sub { color:var(--dim); font-size:14px; margin-top:8px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:20px; margin-top:28px;
          box-shadow:0 18px 50px rgba(0,0,0,.45); }
  .urlwrap { display:flex; align-items:center; gap:10px; background:#0a0a12; border:1px solid var(--line);
             border-radius:14px; padding:4px 6px 4px 16px; transition:border-color .2s; }
  .urlwrap:focus-within { border-color:var(--a1); }
  input[type=url] { flex:1; background:none; border:none; outline:none; color:var(--txt); font-size:15px; padding:12px 0; min-width:0; }
  input::placeholder { color:#55556a; }
  .go { background:linear-gradient(135deg,var(--a1),var(--a2)); border:none; color:#fff; font-weight:600;
        font-size:14px; padding:11px 18px; border-radius:11px; cursor:pointer; transition:transform .12s, opacity .2s; }
  .go:active { transform:scale(.95); }
  .go:disabled { opacity:.45; cursor:default; }
  .chips { display:flex; gap:8px; margin-top:14px; }
  .chip { flex:1; text-align:center; padding:10px 0; font-size:13px; font-weight:600; color:var(--dim);
          background:#0a0a12; border:1px solid var(--line); border-radius:11px; cursor:pointer; transition:all .15s; }
  .chip.on { color:#fff; border-color:var(--a1); background:rgba(99,102,241,.14); }
  #status { margin-top:22px; display:none; }
  .bar { height:6px; background:#0a0a12; border-radius:99px; overflow:hidden; border:1px solid var(--line); }
  .bar > div { height:100%; width:0%; border-radius:99px; background:linear-gradient(90deg,var(--a1),var(--a2)); transition:width .3s; }
  .stext { font-size:13px; color:var(--dim); margin-top:10px; min-height:18px; }
  .stext.err { color:var(--err); }
  .dl { display:none; margin-top:16px; width:100%; text-align:center; text-decoration:none;
        background:linear-gradient(135deg,#059669,#34d399); color:#04110b; font-weight:700; font-size:15px;
        padding:14px 0; border-radius:13px; }
  .fname { font-size:12px; color:var(--dim); margin-top:10px; word-break:break-all; }
  footer { color:#3d3d50; font-size:11px; letter-spacing:3px; padding:28px 0 20px; font-weight:600; }
</style>
</head>
<body>
<div class="glow"></div>
<main>
  <h1>Downloader</h1>
  <p class="sub">Paste a video link. Get the file.</p>
  <div class="card">
    <div class="urlwrap">
      <input id="url" type="url" placeholder="https://" autocomplete="off" autocapitalize="off" spellcheck="false">
      <button class="go" id="go">Grab</button>
    </div>
    <div class="chips">
      <div class="chip on" data-m="video">Video · MP4</div>
      <div class="chip" data-m="audio">Audio · MP3</div>
    </div>
    <div id="status">
      <div class="bar"><div id="fill"></div></div>
      <div class="stext" id="stext">Starting…</div>
      <a class="dl" id="dl">⬇ Download file</a>
      <div class="fname" id="fname"></div>
    </div>
  </div>
</main>
<footer>DOOMSAGE</footer>
<script>
const S = "{{ secret }}";
let mode = "video", job = null, timer = null;
document.querySelectorAll(".chip").forEach(c => c.onclick = () => {
  document.querySelectorAll(".chip").forEach(x => x.classList.remove("on"));
  c.classList.add("on"); mode = c.dataset.m;
});
const $ = id => document.getElementById(id);
$("go").onclick = async () => {
  const url = $("url").value.trim();
  if (!url) return;
  $("go").disabled = true; $("status").style.display = "block";
  $("dl").style.display = "none"; $("fname").textContent = "";
  $("fill").style.width = "2%"; $("stext").className = "stext"; $("stext").textContent = "Starting…";
  try {
    const r = await fetch(`/${S}/api/start`, {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({url, mode})});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Failed to start");
    job = d.job; timer = setInterval(poll, 1200); poll();
  } catch (e) { fail(e.message); }
};
async function poll() {
  if (!job) return;
  try {
    const r = await fetch(`/${S}/api/status/${job}`);
    const d = await r.json();
    if (d.status === "working") {
      $("fill").style.width = Math.max(3, d.progress) + "%";
      $("stext").textContent = d.progress >= 100 ? "Processing…" : `Downloading… ${d.progress}% ${d.speed||""}`;
    } else if (d.status === "done") {
      clearInterval(timer); $("fill").style.width = "100%";
      $("stext").textContent = "Ready."; $("go").disabled = false;
      $("dl").href = `/${S}/api/file/${job}`; $("dl").style.display = "block";
      $("fname").textContent = d.filename || "";
    } else if (d.status === "error") { clearInterval(timer); fail(d.error || "Download failed"); }
  } catch (e) {}
}
function fail(msg) {
  $("stext").className = "stext err"; $("stext").textContent = msg;
  $("fill").style.width = "0%"; $("go").disabled = false;
}
</script>
</body>
</html>"""

@app.route("/")
def root():
    abort(404)

@app.route(f"/{SECRET}/")
def index():
    return render_template_string(PAGE, secret=SECRET)

@app.route(f"/{SECRET}/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")
    if not re.match(r"^https?://", url or ""):
        return jsonify({"error": "Paste a valid link first."}), 400
    jid = uuid.uuid4().hex[:12]
    outdir = os.path.join(DOWNLOAD_DIR, jid)
    os.makedirs(outdir, exist_ok=True)
    JOBS[jid] = {"status": "working", "progress": 0, "speed": "", "filename": None,
                 "title": None, "error": None, "created": time.time()}
    threading.Thread(target=run_download, args=(jid, url, mode, outdir), daemon=True).start()
    return jsonify({"job": jid})

def make_hook(jid):
    def h(d):
        job = JOBS.get(jid)
        if not job:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            if total:
                job["progress"] = max(job["progress"], int(done * 98 / total))
            job["speed"] = (d.get("_speed_str") or "").strip()
        elif d.get("status") == "finished":
            job["progress"] = 100
    return h

def run_download(jid, url, mode, outdir):
    import yt_dlp
    job = JOBS[jid]
    opts = {
        "outtmpl": os.path.join(outdir, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [make_hook(jid)],
        "quiet": True, "no_warnings": True,
        "socket_timeout": 30, "retries": 3,
        "restrictfilenames": True,
    }
    if mode == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                   "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
        opts["merge_output_format"] = "mp4"
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            job["title"] = info.get("title")
        files = [f for f in os.listdir(outdir) if os.path.isfile(os.path.join(outdir, f))]
        if not files:
            raise RuntimeError("No file was produced.")
        job["filename"] = max(files, key=lambda f: os.path.getsize(os.path.join(outdir, f)))
        job["status"] = "done"
    except Exception as e:
        msg = str(e).replace("\n", " ")
        if "Sign in to confirm" in msg or "bot" in msg.lower():
            msg = "This site blocked the download (bot check). Try another link or source."
        job["status"] = "error"
        job["error"] = msg[:280]

@app.route(f"/{SECRET}/api/status/<jid>")
def status(jid):
    job = JOBS.get(jid)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(job)

@app.route(f"/{SECRET}/api/file/<jid>")
def file(jid):
    job = JOBS.get(jid)
    if not job or job["status"] != "done":
        abort(404)
    return send_from_directory(os.path.join(DOWNLOAD_DIR, jid), job["filename"], as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
