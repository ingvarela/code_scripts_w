import argparse, os
from yt_dlp import YoutubeDL

def on_progress(d):
    if d.get('status') == 'downloading':
        p = d.get('_percent_str', '').strip()
        s = d.get('_speed_str', '').strip()
        eta = d.get('_eta_str', '').strip()
        print(f"\r{p} {s} ETA {eta}", end='', flush=True)
    elif d.get('status') == 'finished':
        print(f"\nSaved to: {d.get('filename')}")

def download(url, audio=False, outtmpl=None, allow_playlist=False):
    ydl_opts = {
        "outtmpl": outtmpl or "%(title).200B [%(id)s].%(ext)s",
        "noplaylist": not allow_playlist,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
        "continuedl": True,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [on_progress],
    }
    if audio:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        })
    else:
        ydl_opts.update({
            "format": "bv*+ba/best",      # best video+audio
            "merge_output_format": "mp4"  # container for merged streams
        })

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Download YouTube videos with yt-dlp")
    ap.add_argument("url", help="YouTube video or playlist URL")
    ap.add_argument("--audio", action="store_true", help="Audio-only (MP3)")
    ap.add_argument("--playlist", action="store_true", help="Allow downloading entire playlist")
    ap.add_argument("--out", default="downloads/%(title).200B [%(id)s].%(ext)s",
                    help="Output path/template")
    args = ap.parse_args()

    # Ensure target directory exists if you use a folder in --out
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    download(args.url, audio=args.audio, outtmpl=args.out, allow_playlist=args.playlist)
