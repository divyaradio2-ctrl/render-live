import os
import time
import threading
import requests
import subprocess
from flask import Flask, request, render_template_string
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
stream_running = False
ffmpeg_process = None
match_index = 0

MAX_DURATION = 604800

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Render Direct 24/7 Live</title>
    <style>
        body { font-family: Arial, sans-serif; background: #070b14; color: white; padding: 20px; text-align: center; }
        .box { max-width: 460px; margin: auto; background: #111827; padding: 25px; border-radius: 14px; border: 1px solid #1f2937; }
        input { width: 92%; padding: 15px; margin: 12px 0; border-radius: 8px; border: 1px solid #374151; background: #1f2937; color: white; font-size: 16px; text-align: center; }
        button { width: 98%; padding: 16px; font-size: 18px; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; margin-top: 10px; }
        .start { background: #16a34a; color: white; }
        .stop { background: #dc2626; color: white; }
        .status { padding: 14px; background: #1e293b; border-radius: 8px; margin-bottom: 15px; color: #38bdf8; font-size: 15px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🌍 Render 24/7 Sports Live</h2>
        <div class="status">Status: <b>{{ status }}</b></div>
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

def get_worldwide_matches():
    matches = []
    for sport_label, url in FEEDS:
        try:
            res = requests.get(url, timeout=8).json()
            for ev in res.get("events", []):
                state = ev.get("status", {}).get("type", {}).get("state", "")
                if state in ["in", "pre", "post"]:
                    name = ev.get("shortName", ev.get("name", "LIVE MATCH"))
                    status_detail = ev.get("status", {}).get("type", {}).get("shortDetail", "Live Updates")
                    comp = ev.get("competitions", [{}])
                    competitors = comp[0].get("competitors", []) if comp else []
                    score_str = "Match Starting Soon"
                    if len(competitors) >= 2:
                        t1 = competitors[0].get("team", {}).get("abbreviation", "TEAM 1")
                        s1 = competitors[0].get("score", "0")
                        t2 = competitors[1].get("team", {}).get("abbreviation", "TEAM 2")
                        s2 = competitors[1].get("score", "0")
                        score_str = f"{t1}  {s1}   vs   {t2}  {s2}"
                    item = (sport_label, name[:42], score_str[:38], status_detail[:50], state == "in")
                    if state == "in":
                        matches.insert(0, item)
                    else:
                        matches.append(item)
        except Exception:
            continue
    if not matches:
        matches.append(("WORLDWIDE SPORTS LIVE", "Scanning Global Matches...", "FOOTBALL & CRICKET", "Next Match Starting Soon", False))
    return matches[:10]

def make_scoreboard_image(sport, match_name, score, detail, is_live):
    img = Image.new("RGB", (1280, 720), color=(9, 13, 26))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(15, 15), (1265, 705)], outline=(56, 189, 248), width=5)
    draw.rectangle([(15, 15), (1265, 125)], fill=(2, 132, 199))
    draw.rectangle([(60, 165), (1220, 515)], fill=(17, 24, 39), outline=(55, 65, 81), width=3)
    try:
        f_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 58)
        f_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        f_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        f_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except Exception:
        f_xl = f_lg = f_md = f_sm = ImageFont.load_default()
    live_badge = "● LIVE NOW" if is_live else "● SCOREBOARD"
    draw.text((60, 48), f"{live_badge}  |  {sport}", fill=(255, 255, 255), font=f_lg)
    draw.text((100, 195), match_name, fill=(250, 204, 21), font=f_lg)
    draw.text((100, 295), score, fill=(255, 255, 255), font=f_xl)
    status_color = (74, 222, 128) if is_live else (56, 189, 248)
    draw.text((100, 425), f"STATUS: {detail}", fill=status_color, font=f_md)
    draw.text((60, 565), "🌍 24/7 Worldwide Football & Cricket Live Scores", fill=(226, 232, 240), font=f_md)
    draw.text((60, 625), "Auto-Updates Every 15 Seconds  •  Subscribe & Comment Your Team!", fill=(148, 163, 184), font=f_sm)
    img.save("temp.png")
    os.replace("temp.png", "scoreboard.png")

def start_ffmpeg(rtmp_url, remaining_time):
    cmd = [
        "ffmpeg", "-re", "-loop", "1", "-framerate", "2", "-i", "scoreboard.png",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1500k", "-maxrate", "1500k",
        "-bufsize", "3000k", "-pix_fmt", "yuv420p", "-g", "4",
        "-c:a", "aac", "-b:a", "128k", "-t", str(int(remaining_time)), "-f", "flv", rtmp_url
    ]
    return subprocess.Popen(cmd)

def keep_alive_pinger():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        time.sleep(600)
        if render_url:
            try:
                requests.get(render_url, timeout=5)
            except Exception:
                pass

def run_stream_worker(yt_key):
    global stream_running, ffmpeg_process, match_index
    clean_key = yt_key.strip().split("/")[-1]
    rtmp = f"rtmp://://youtube.com{clean_key}"
    make_scoreboard_image("WORLDWIDE SPORTS", "Starting 24/7 Live Stream...", "LOADING SCORES", "Connecting to Global Server", True)
    start_t = time.time()
    ffmpeg_process = start_ffmpeg(rtmp, MAX_DURATION)
    while stream_running and (time.time() - start_t < MAX_DURATION):
        if ffmpeg_process.poll() is not None:
            rem = MAX_DURATION - (time.time() - start_t)
            if rem > 10:
                ffmpeg_process = start_ffmpeg(rtmp, rem)
        matches = get_worldwide_matches()
        current = matches[match_index % len(matches)]
        make_scoreboard_image(current[0], current[1], current[2], current[3], current[4])
        match_index += 1
        time.sleep(15)
    if ffmpeg_process:
        ffmpeg_process.terminate()
    stream_running = False

@app.route("/", methods=["GET"])
def home():
    msg = "🟢 LIVE CHAL RAHA HAI (24/7 Non-Stop)" if stream_running else "🔴 BAND HAI (Stream Key daal kar Start karein)"
    return render_template_string(HTML_PAGE, status=msg)

@app.route("/start", methods=["POST"])
def start():
    global stream_running
    if not stream_running:
        stream_running = True
        yt = request.form["yt_key"].strip()
        threading.Thread(target=run_stream_worker, args=(yt,), daemon=True).start()
    return home()

@app.route("/stop", methods=["POST"])
def stop():
    global stream_running, ffmpeg_process
    stream_running = False
    if ffmpeg_process:
        ffmpeg_process.terminate()
    return home()

if __name__ == "__main__":
    threading.Thread(target=keep_alive_pinger, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
