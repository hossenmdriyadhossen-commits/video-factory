import os, json, asyncio, subprocess, urllib.parse, urllib.request, time, random, math
from pathlib import Path
import edge_tts
from PIL import Image, ImageDraw

W, H, FPS = 1080, 1920, 30
spec = json.loads(os.environ["SPEC"])
OUT = Path("out"); OUT.mkdir(exist_ok=True)
WORK = Path("work"); WORK.mkdir(exist_ok=True)

VOICES = {"female": "bn-BD-NabanitaNeural", "male": "bn-BD-PradeepNeural"}
STYLES = {"normal": ("+0%", "+0Hz", "+0%"), "slow": ("-14%", "-2Hz", "+0%"), "whisper": ("-18%", "-6Hz", "-35%"), "excited": ("+10%", "+4Hz", "+8%")}
GRADES = {
    "warm": "eq=contrast=1.08:saturation=1.15,colorbalance=rs=0.06:bs=-0.06",
    "cool": "eq=contrast=1.06:saturation=1.05,colorbalance=rs=-0.05:bs=0.07",
    "noir": "eq=contrast=1.2:saturation=0.65:brightness=-0.03",
    "vivid": "eq=contrast=1.08:saturation=1.35",
}

def run(cmd):
    print(" ".join(cmd)[:400], flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-2500:], flush=True)
        raise RuntimeError("command failed: " + cmd[0])
    return p.stdout

def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]).strip())

async def tts(text, voice, style, path):
    rate, pitch, vol = STYLES.get(style, STYLES["normal"])
    for attempt in range(5):
        try:
            c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=vol)
            await c.save(str(path))
            if path.exists() and path.stat().st_size > 1000:
                return
        except Exception as e:
            print("tts retry", attempt, e, flush=True)
            await asyncio.sleep(3)
    raise RuntimeError("TTS failed")

def fetch_image(prompt, path, seed):
    q = urllib.parse.quote(prompt + ", cinematic, photorealistic, dramatic lighting, ultra detailed, vertical composition")
    url = "https://image.pollinations.ai/prompt/" + q + "?width=1080&height=1920&model=flux&nologo=true&seed=" + str(seed)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=120).read()
            if len(data) > 20000:
                path.write_bytes(data)
                Image.open(path).convert("RGB").save(path, quality=95)
                return True
        except Exception as e:
            print("image retry", attempt, e, flush=True)
        time.sleep(4 + attempt * 5)
    return False

def fallback_image(path, i):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    c1 = [(18, 24, 38), (60, 30, 70), (20, 50, 60), (70, 40, 30)][i % 4]
    c2 = (5, 5, 10)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c1[k] * (1 - t) + c2[k] * t) for k in range(3)))
    img.save(path, quality=92)

def make_scene(i, img, dur, anim, grade):
    frames = int(round(dur * FPS))
    if anim == "zoom_out":
        z = "if(eq(on,0),1.22,max(zoom-0.0006,1.0))"
    else:
        z = "min(zoom+0.0006,1.22)"
    vf = ("scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
          "zoompan=z='" + z + "':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=" + str(frames) + ":s=1080x1920:fps=30,"
          + GRADES[grade] + ",vignette=PI/5,noise=alls=5:allf=t,"
          "fade=t=in:st=0:d=0.25,fade=t=out:st=" + format(dur - 0.25, ".3f") + ":d=0.25,format=yuv420p")
    out = WORK / ("scene" + str(i) + ".mp4")
    run(["ffmpeg", "-y", "-i", str(img), "-vf", vf, "-frames:v", str(frames), "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(out)])
    return out

def ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)

def chunks(text, n=4):
    words = text.split()
    return [" ".join(words[i:i + n]) for i in range(0, len(words), n)] or [text]

ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Noto Sans Bengali,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,70,70,360,1
Style: Hook,Noto Sans Bengali,110,&H0000D4FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,3,8,70,70,230,1
Style: Thumb,Noto Sans Bengali,150,&H0000D4FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,11,4,2,60,60,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def clean(t):
    return t.replace("{", "(").replace("}", ")").replace("\n", " ")

def make_thumb(first_img, hook):
    ass = ASS_HEAD + "Dialogue: 0,0:00:00.00,0:00:05.00,Thumb,,0,0,0,," + clean(hook) + "\n"
    Path("work/thumb.ass").write_text(ass, encoding="utf-8")
    vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.12:saturation=1.2,"
          "drawbox=x=0:y=ih*0.42:w=iw:h=ih*0.58:color=black@0.5:t=fill,"
          "subtitles=work/thumb.ass:fontsdir=/usr/share/fonts")
    run(["ffmpeg", "-y", "-i", str(first_img), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(OUT / "thumb.jpg")])

async def main():
    scenes = spec["scenes"]
    voice = VOICES.get(spec.get("voice", "female"), VOICES["female"])
    grade = spec.get("grade") if spec.get("grade") in GRADES else "warm"
    hook = spec.get("hook") or spec.get("title", "")
    t0 = 0.0
    events = []
    scene_files = []
    wavs = []
    first_img = None
    for i, s in enumerate(scenes):
        mp3 = WORK / ("s" + str(i) + ".mp3")
        await tts(s["narration"], voice, s.get("voice_style", "normal"), mp3)
        vd = duration(mp3)
        dur = math.ceil((vd + 0.45) * FPS) / FPS
        img = WORK / ("s" + str(i) + ".jpg")
        if not fetch_image(s["image_prompt"], img, random.randint(1, 99999)):
            fallback_image(img, i)
        if first_img is None:
            first_img = img
        scene_files.append(make_scene(i, img, dur, s.get("animation", "zoom_in"), grade))
        wav = WORK / ("s" + str(i) + ".wav")
        run(["ffmpeg", "-y", "-i", str(mp3), "-af", "apad=pad_dur=2,atrim=0:" + format(dur, ".3f"), "-ar", "48000", "-ac", "1", str(wav)])
        wavs.append(wav)
        chs = chunks(s["narration"])
        total = sum(len(c) for c in chs) or 1
        cur = t0 + 0.05
        span = vd
        for c in chs:
            d = span * len(c) / total
            events.append("Dialogue: 0,%s,%s,Sub,,0,0,0,,%s" % (ts(cur), ts(cur + d), clean(c)))
            cur += d
        t0 += dur
    events.append("Dialogue: 0,0:00:00.10,0:00:02.60,Hook,,0,0,0,," + r"{\fad(200,300)}" + clean(hook))
    Path("work/sub.ass").write_text(ASS_HEAD + "\n".join(events) + "\n", encoding="utf-8")

    Path("work/vlist.txt").write_text("".join("file '" + str(f.resolve()) + "'\n" for f in scene_files))
    Path("work/alist.txt").write_text("".join("file '" + str(f.resolve()) + "'\n" for f in wavs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "work/vlist.txt", "-c", "copy", "work/video_raw.mp4"])
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "work/alist.txt", "-c", "copy", "work/voice_all.wav"])
    total_dur = duration("work/video_raw.mp4")

    voice_chain = ("[1:a]highpass=f=70,lowpass=f=12000,equalizer=f=3000:t=q:w=1:g=2,"
                   "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:makeup=3,aecho=0.8:0.6:35:0.10[v]")
    bed_chain = "[2:a][3:a]amix=inputs=2:normalize=0,tremolo=f=0.15:d=0.5,lowpass=f=420,volume=0.04[bed]"
    mix = "[v][bed]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    sub = "[0:v]subtitles=work/sub.ass:fontsdir=/usr/share/fonts[vv]"
    run(["ffmpeg", "-y", "-i", "work/video_raw.mp4", "-i", "work/voice_all.wav",
         "-f", "lavfi", "-i", "sine=f=110:r=48000", "-f", "lavfi", "-i", "sine=f=165:r=48000",
         "-filter_complex", ";".join([voice_chain, bed_chain, mix, sub]),
         "-map", "[vv]", "-map", "[a]", "-t", format(total_dur, ".3f"),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUT / "video.mp4")])
    make_thumb(first_img, hook)
    (OUT / "meta.json").write_text(json.dumps({"title": spec.get("title"), "duration": total_dur, "voice": voice, "grade": grade}, ensure_ascii=False))
    print("DONE", total_dur, flush=True)

asyncio.run(main())
