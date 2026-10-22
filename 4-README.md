# dg-downloader

Private personal video downloader. Single-page web UI over yt-dlp, served behind an
unguessable URL path (no login). Deploys as one Docker container.

- Video (MP4, up to 1080p) or audio (MP3) from any yt-dlp-supported site
- Files are temporary: auto-deleted 30 minutes after download
- Free-tier friendly (single gunicorn worker, threaded downloads)

Set `DG_SECRET` (8-64 chars of a-z 0-9 -). The app only serves under `/<DG_SECRET>/`; everything else 404s. No secret in this repo.

Personal use only. Downloading copyrighted content without permission is illegal;
YouTube downloads are against YouTube's Terms of Service.
