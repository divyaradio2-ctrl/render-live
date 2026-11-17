import os
import time
import threading
import requests
import subprocess
from flask import Flask, request, render_template_string
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
stream_proc = None
status_msg = "Ready (Final v3.0)"
match_idx = 0

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Render Live v3</title>
    <style>
        body { font-family: Arial, sans-serif; background: #070b14; color: white; padding: 20px; text-align: center; }
        .box { max-width: 460px; margin: auto; background: #111827; padding: 25px; border-radius: 14px; border: 1px solid #1f2937; }
        input { width: 92%; padding: 15px; margin: 12px 0; border-radius: 8px; border: 1px solid #374151; background: #1f2937; color: white; font-size: 16px; text-align: center; }
        button { width: 98%; padding: 16px; font-size: 18px; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; margin-top: 10px; }
        .start { background: #16a34a; color: white; }
        .stop { background: #dc2626; color: white; }
        .status { padding: 14px; background: #1e293b; border-radius: 8px; margin-bottom: 15px; color: #38bdf8; font-size: 14px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🌍 Render 24/7 Sports Live</h2>
        <div class="status">Status: <b>{{ st }}</b></div>
        <form method="POST" action="/start">
            <input type="text" name="yt_key" placeholder="यहाँ अपनी YouTube Stream Key डालें" required><br>
            <button type="submit" class="start">▶ START NON-STOP LIVE</button>
        </form>
        <form method="POST" action="/stop">
            <button type="submit" class="stop">⏹ STOP STREAM</button>
        </form>
    </div>
</body>
</html>
"""

FEEDS = [
    ("FOOTBALL • TOP LEAGUES", "https://espn.com"),
    ("CRICKET • INTERNATIONAL", "https://espn.com"),
    ("CRICKET • WORLD SERIES", "https://espn.com")
]

def update_image():
    global match_idx
    matches = []
    for label, url in FEEDS:
        try:
            res = requests.get(url, timeout=6).json()
            for ev in res.get("events", []):
                state = ev.get("status", {}).get("type", {}).get("state", "")
                if state in ["in", "pre", "post"]:
                    name = ev.get("shortName", "LIVE MATCH")
                    detail = ev.get("status", {}).get("type", {}).get("shortDetail", "Live")
                    comp = ev.get("competitions", [{}])
                    competitors = comp[0].get("competitors", []) if comp else []
                    score = "Match Starting Soon"
                    if len(competitors) >= 2:
                        t1 = competitors[0].get("team", {}).get("abbreviation", "T1")
                        s1 = competitors[0].get("score", "0")
                        t2 = competitors[1].get("team", {}).get("abbreviation", "T2")
                        s2 = competitors[1].get("score", "0")
                        score = f"{t1}  {s1}   vs   {t2}  {s2}"
                    matches.append((label, name[:38], score[:34], detail[:45], state == "in"))
        except Exception:
            pass

    if not matches:
        matches = [("WORLDWIDE SPORTS LIVE", "Football & Cricket Live", "24/7 SCOREBOARD", "Updating Live Scores...", True)]

    sport, name, score, detail, is_live = matches[match_idx % len(matches)]
    match_idx += 1

    img = Image.new("RGB", (854, 480), color=(9, 13, 26))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(10, 10), (844, 470)], outline=(56, 189, 248), width=4)
    draw.rectangle([(10, 10), (844, 85)], fill=(2, 132, 199))
    draw.rectangle([(40, 110), (814, 345)], fill=(17, 24, 39), outline=(55, 65, 81), width=2)
    try:
        f_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        f_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        f_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
        f_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    except Exception:
        f_xl = f_lg = f_md = f_sm = ImageFont.load_default()

    draw.text((35, 32), f"{'● LIVE' if is_live else '● SCORE'}  |  {sport}", fill=(255, 255, 255), font=f_lg)
    draw.text((65, 130), name, fill=(250, 204, 21), font=f_lg)
    draw.text((65, 195), score, fill=(255, 255, 255), font=f_xl)
    draw.text((65, 285), f"STATUS: {detail}", fill=(74, 222, 128), font=f_md)
    draw.text((40, 380), "🌍 24/7 Worldwide Football & Cricket Live Scores", fill=(226, 232, 240), font=f_md)
    draw.text((40, 420), "Auto-Updates Every 15 Seconds  •  Subscribe!", fill=(148, 163, 184), font=f_sm)

    img.save("temp.png")
    os.replace("temp.png", "scoreboard.png")

def bg_updater():
    while True:
        try:
            update_image()
        except Exception:
            pass
        time.sleep(15)

def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        time.sleep(600)
        if url:
            try:
                requests.get(url, timeout=5)
            except Exception:
                pass

@app.route("/", methods=["GET"])
def home():
    global stream_proc, status_msg
    if stream_proc is not None:
        if stream_proc.poll() is None:
            status_msg = "🟢 100% LIVE CHAL RAHA HAI!"
        else:
            err = stream_proc.stderr.read() if stream_proc.stderr else ""
            status_msg = "🔴 Band Ho Gaya: " + (err[-100:] if err else "Check Stream Key")
            stream_proc = None
    return render_template_string(HTML_PAGE, st=status_msg)

@app.route("/start", methods=["POST"])
def start():
    global stream_proc, status_msg
    if stream_proc is not None and stream_proc.poll() is None:
        return home()

    update_image()
    key = request.form["yt_key"].strip().split("/")[-1]
    rtmp = f"rtmp://://youtube.com{key}"

    cmd = [
        "ffmpeg", "-re", "-loop", "1", "-framerate", "1", "-i", "scoreboard.png",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-threads", "1", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
        "-b:v", "600k", "-maxrate", "600k", "-bufsize", "1200k", "-pix_fmt", "yuv420p", "-g", "2",
        "-c:a", "aac", "-b:a", "64k", "-f", "flv", rtmp
    ]
    stream_proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    return home()

@app.route("/stop", methods=["POST"])
def stop():
    global stream_proc, status_msg
    if stream_proc is not None:
        stream_proc.terminate()
        stream_proc = None
    status_msg = "⏹ Stopped by User"
    return home()

if __name__ == "__main__":
    update_image()
    threading.Thread(target=bg_updater, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
