import argparse, os, sys, time, random
from yt_dlp import YoutubeDL

def on_progress(d):
    if d.get('status') == 'downloading':
        p = d.get('_percent_str', '').strip()
        s = d.get('_speed_str', '').strip()
        eta = d.get('_eta_str', '').strip()
        print(f"\r{p} {s} ETA {eta}", end='', flush=True)
    elif d.get('status') == 'finished':
        print(f"\nSaved to: {d.get('filename')}")

def download(url, audio=False, outtmpl=None, allow_playlist=False,
             rate_limit_bps=1_000_000, min_sleep=2, max_sleep=5):
    """
    rate_limit_bps: bytes/sec (e.g., 1_000_000 ≈ 1 MB/s)
    min_sleep/max_sleep: seconds to pause (random) before each download starts
    """

    # Gentle, single-stream settings; no geo bypass tricks, no cookies.
    ydl_opts = {
        "outtmpl": outtmpl or "%(title).200B [%(id)s].%(ext)s",
        "noplaylist": not allow_playlist,     # never pull entire playlists unless explicitly allowed
        "ignoreerrors": False,                # fail fast instead of hammering broken links
        "retries": 3,
        "fragment_retries": 3,
        "continuedl": True,                   # resume if interrupted
        "concurrent_fragment_downloads": 1,   # single fragment at a time
        "ratelimit": rate_limit_bps,          # cap throughput to be polite
        "sleep_interval": min_sleep,          # yt-dlp will sleep between items
        "max_sleep_interval": max_sleep,      # add jitter
        "socket_timeout": 30,
        "restrictfilenames": True,
        "progress_hooks": [on_progress],
    }

    if audio:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts.update({
            "format": "bv*+ba/best",
            "merge_output_format": "mp4",
        })

    # Small, extra pause before contacting the site (polite & jittered).
    time.sleep(random.uniform(min_sleep, max_sleep))

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Polite, compliance-first YouTube downloader (yt-dlp)")
    ap.add_argument("url", help="YouTube video or playlist URL")
    ap.add_argument("--audio", action="store_true", help="Audio-only (MP3; requires ffmpeg)")
    ap.add_argument("--playlist", action="store_true", help="Allow downloading entire playlist")
    ap.add_argument("--out", default="downloads/%(title).200B [%(id)s].%(ext)s",
                    help="Output path/template")
    ap.add_argument("--rate", type=str, default="1M",
                    help="Rate limit (e.g., 500K, 1M, 2M). Default: 1M")
    ap.add_argument("--min-sleep", type=float, default=2.0, help="Min sleep before downloads (s)")
    ap.add_argument("--max-sleep", type=float, default=5.0, help="Max sleep before downloads (s)")
    ap.add_argument("--i-understand-tos", action="store_true",
                    help="Required: you confirm you have rights/permission and will follow YouTube ToS")
    args = ap.parse_args()

    if not args.i_understand_tos:
        sys.exit("Refusing to run. Re-run with --i-understand-tos after confirming you have rights and will follow YouTube's Terms.")

    # Parse human-friendly rate like "500K"/"1M" to bytes/s
    units = {"K": 1024, "M": 1024*1024}
    rate_arg = args.rate.upper().strip()
    if rate_arg[-1] in units:
        rate_bps = int(float(rate_arg[:-1]) * units[rate_arg[-1]])
    else:
        rate_bps = int(float(rate_arg))  # raw bytes/sec

    # Ensure target dir exists if template includes a folder
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Keep jitter sane
    min_sleep = max(0.0, args.min_sleep)
    max_sleep = max(min_sleep, args.max_sleep)

    download(
        args.url,
        audio=args.audio,
        outtmpl=args.out,
        allow_playlist=args.playlist,
        rate_limit_bps=rate_bps,
        min_sleep=min_sleep,
        max_sleep=max_sleep
    )
