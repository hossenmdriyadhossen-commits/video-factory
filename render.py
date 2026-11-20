import os, json, subprocess, urllib.parse, urllib.request, time, random, math, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 1080, 1920, 30
D = 4.2
X = 0.5
spec = json.loads(os.environ["SPEC"])
OUT = Path("out"); OUT.mkdir(exist_ok=True)
WORK = Path("work"); WORK.mkdir(exist_ok=True)
FONT = "DejaVu Sans"

GRADES = {
    "cool": "eq=contrast=1.10:saturation=1.10,colorbalance=rs=-0.05:bs=0.08",
    "warm": "eq=contrast=1.10:saturation=1.15,colorbalance=rs=0.07:bs=-0.06",
    "noir": "eq=contrast=1.22:saturation=0.70:brightness=-0.03",
    "vivid": "eq=contrast=1.10:saturation=1.40",
    "teal_orange": "eq=contrast=1.12:saturation=1.20,colorbalance=rs=0.08:gs=-0.02:bs=-0.08:rh=-0.06:bh=0.08",
}
ACCENTS = {"cool": "00E5FF", "warm": "FFB020", "noir": "FFFFFF", "vivid": "FF3D81", "teal_orange": "FF8A00"}
TRANS = ["slideleft", "wipeup", "circleopen", "smoothleft", "zoomin", "fadewhite", "slideup", "radial", "dissolve", "wiperight"]
ANIMS = ["zoom_in", "pan_left", "zoom_out", "pan_right"]


def run(cmd):
    print(" ".join(str(c) for c in cmd)[:500], flush=True)
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-3000:], flush=True)
        raise RuntimeError("command failed: " + str(cmd[0]))
    return p.stdout


def ass_color(hexrgb, alpha="00"):
    r, g, b = hexrgb[0:2], hexrgb[2:4], hexrgb[4:6]
    return "&H" + alpha + b + g + r + "&"


def fetch_image(prompt, path, seed):
    if os.environ.get("NOIMG"):
        return False
    q = urllib.parse.quote(prompt + ", cinematic, ultra detailed, dramatic lighting, sharp focus, vertical composition, no text, no watermark")
    url = "https://image.pollinations.ai/prompt/" + q + "?width=1080&height=1920&model=flux&nologo=true&seed=" + str(seed)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            if len(data) > 20000:
                path.write_bytes(data)
                Image.open(path).convert("RGB").save(path, quality=95)
                return True
        except Exception as e:
            print("image retry", attempt, e, flush=True)
        time.sleep(3 + attempt * 4)
    return False


def fallback_image(path, i, accent):
    base = [(10, 14, 30), (22, 10, 36), (8, 28, 36), (30, 16, 20)][i % 4]
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img, "RGBA")
    ac = tuple(int(accent[k:k + 2], 16) for k in (0, 2, 4))
    rnd = random.Random(i * 7 + 3)
    for _ in range(14):
        cx, cy, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(120, 520)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ac + (rnd.randint(10, 38),))
    for gx in range(0, W, 90):
        d.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 10), width=1)
    for gy in range(0, H, 90):
        d.line([(0, gy), (W, gy)], fill=(255, 255, 255, 10), width=1)
    img = img.filter(ImageFilter.GaussianBlur(6))
    img.save(path, quality=92)


def make_gradient(path):
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = g.load()
    for y in range(H):
        t = max(0.0, (y - H * 0.38) / (H * 0.62))
        a = int(215 * (t ** 1.4))
        top = int(70 * max(0.0, 1 - y / (H * 0.18)))
        for x in range(W):
            px[x, y] = (0, 0, 0, max(a, top))
    g.save(path)


def make_scene(i, img, anim, grade):
    n = int(round(D * FPS))
    base = "scale=1782:3168:force_original_aspect_ratio=increase,crop=1782:3168,"
    if anim == "zoom_out":
        z, x, y = "1.25-0.25*on/" + str(n), "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    elif anim == "pan_left":
        z, x, y = "1.22", "(iw-iw/zoom)*(1-on/" + str(n) + ")", "ih/2-ih/zoom/2"
    elif anim == "pan_right":
        z, x, y = "1.22", "(iw-iw/zoom)*on/" + str(n), "ih/2-ih/zoom/2"
    else:
        z, x, y = "1+0.25*on/" + str(n), "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
    vf = base + "zoompan=z='" + z + "':x='" + x + "':y='" + y + "':d=" + str(n) + ":s=1080x1920:fps=30,format=yuv420p"
    out = WORK / ("scene" + str(i) + ".mp4")
    run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", n, "-r", FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out])
    return out


def ts(t):
    t = max(t, 0)
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def wrap(text, width):
    lines = textwrap.wrap(text.strip(), width=width, break_long_words=False)
    return lines[:3] if lines else [text]


def esc(t):
    return t.replace("{", "(").replace("}", ")").replace("\\", "")


def build_ass(scenes, total, accent, tag):
    ac = ass_color(accent)
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Head,%s,92,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,7,3,8,60,60,0,1
Style: Sub,%s,50,&H00E6E6E6,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,4,2,8,70,70,0,1
Style: Tag,%s,36,&H00101010,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,3,0,1,0,0,5,0,0,0,1
Style: Shape,%s,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" % (FONT, FONT, FONT, FONT)
    ev = []
    ev.append("Dialogue: 1,%s,%s,Shape,,0,0,0,,{\\an7\\pos(0,1896)\\p1\\1c&HFFFFFF&\\1a&HC0&}m 0 0 l 1080 0 1080 10 0 10" % (ts(0), ts(total)))
    ev.append("Dialogue: 2,%s,%s,Shape,,0,0,0,,{\\an7\\pos(0,1896)\\p1\\1c%s\\fscx1\\t(0,%d,\\fscx100)}m 0 0 l 1080 0 1080 10 0 10" % (ts(0), ts(total), ac, int(total * 1000)))
    tg = esc(tag.upper())
    cw = int(40 + len(tg) * 26)
    ev.append("Dialogue: 2,%s,%s,Shape,,0,0,0,,{\\an7\\move(-%d,150,60,150,0,350)\\p1\\1c%s}m 0 0 l %d 0 %d 62 0 62" % (ts(0), ts(total), cw, ac, cw, cw))
    ev.append("Dialogue: 3,%s,%s,Tag,,0,0,0,,{\\an5\\move(%d,181,%d,181,0,350)}%s" % (ts(0), ts(total), -cw // 2, 60 + cw // 2, tg))
    for i, s in enumerate(scenes):
        st = i * (D - X) + 0.15
        en = total if i == len(scenes) - 1 else i * (D - X) + D - X + 0.05
        lines = [l.upper() for l in wrap(esc(s["headline"]), 15)]
        words = lines[-1].split(" ")
        words[-1] = "{\\1c%s}%s{\\1c&HFFFFFF&}" % (ac, words[-1])
        lines[-1] = " ".join(words)
        htxt = "\\N".join(lines)
        y0 = 940
        ev.append("Dialogue: 2,%s,%s,Shape,,0,0,0,,{\\an7\\pos(455,%d)\\p1\\1c%s\\fscx1\\t(0,400,\\fscx100)}m 0 0 l 170 0 170 12 0 12" % (ts(st), ts(en), y0 - 30, ac))
        ev.append("Dialogue: 3,%s,%s,Head,,0,0,0,,{\\an8\\move(540,%d,540,%d,0,320)\\fscx88\\fscy88\\alpha&HFF&\\t(0,320,\\fscx100\\fscy100\\alpha&H00&)}%s" % (ts(st), ts(en), y0 + 40, y0, htxt))
        sub = esc(s.get("sub", "")).strip()
        if sub:
            sl = wrap(sub, 30)
            ys = y0 + len(lines) * 108 + 36
            ev.append("Dialogue: 3,%s,%s,Sub,,0,0,0,,{\\an8\\pos(540,%d)\\alpha&HFF&\\t(260,620,\\alpha&H00&)}%s" % (ts(st), ts(en), ys, "\\N".join(sl)))
    return head + "\n".join(ev) + "\n"


def make_music(total, bpm, minor, path, n_trans):
    beat = 60.0 / bpm
    root = 55.0 if minor else 65.41
    third = 1.189207 if minor else 1.259921
    fifth = 1.498307
    r2 = root * 4
    kick = "sin(2*PI*(45+120*exp(-38*mod(t,%.4f)))*mod(t,%.4f))*exp(-7*mod(t,%.4f))*0.55" % (beat, beat, beat)
    hat = "(random(0)*2-1)*exp(-60*mod(t+%.4f,%.4f))*0.10" % (beat / 2, beat / 2)
    bass = "sin(2*PI*%.2f*t)*0.20*(0.55+0.45*sin(2*PI*t/%.4f))" % (root, beat * 2)
    pad = "(sin(2*PI*%.2f*t)+sin(2*PI*%.2f*t)+sin(2*PI*%.2f*t))*0.045*(0.75+0.25*sin(2*PI*0.18*t))" % (r2, r2 * third, r2 * fifth)
    step = beat / 2
    idx = "floor(mod(t,%.4f)/%.4f)" % (step * 8, step)
    pat = "if(lt(%s,1),0,if(lt(%s,2),7,if(lt(%s,3),12,if(lt(%s,4),7,if(lt(%s,5),%d,if(lt(%s,6),7,if(lt(%s,7),12,%d)))))))" % (idx, idx, idx, idx, idx, 3 if minor else 4, idx, idx, 15 if minor else 16)
    arp = "sin(2*PI*%.2f*pow(2,(%s)/12)*t)*0.07*exp(-5*mod(t,%.4f))" % (r2 * 2, pat, step)
    expr = "%s+%s+%s+%s+%s" % (kick, hat, bass, pad, arp)
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "aevalsrc='" + expr + "':s=44100:c=stereo:d=" + format(total, ".3f")]
    for k in range(n_trans):
        cmd += ["-f", "lavfi", "-i", "aevalsrc='(random(1)*2-1)*0.9*pow(sin(PI*t/0.6),2)':s=44100:c=stereo:d=0.6"]
    fc = ["[0:a]lowpass=f=8000,volume=0.9[m]"]
    labels = ["[m]"]
    for k in range(n_trans):
        t_ms = int(((k + 1) * (D - X) - 0.25) * 1000)
        fc.append("[%d:a]highpass=f=900,lowpass=f=7000,volume=0.55,adelay=%d|%d[w%d]" % (k + 1, t_ms, t_ms, k))
        labels.append("[w%d]" % k)
    fc.append("".join(labels) + "amix=inputs=%d:duration=first:normalize=0,afade=t=in:d=0.4,afade=t=out:st=%.2f:d=0.9,loudnorm=I=-15:TP=-1.5:LRA=9[a]" % (len(labels), max(total - 0.9, 0)))
    cmd += ["-filter_complex", ";".join(fc), "-map", "[a]", "-ar", 44100, path]
    run(cmd)


def main():
    scenes = spec["scenes"]
    n = len(scenes)
    grade = spec.get("grade") if spec.get("grade") in GRADES else "teal_orange"
    accent = spec.get("accent") if isinstance(spec.get("accent"), str) and len(spec.get("accent", "")) == 6 else ACCENTS[grade]
    tag = spec.get("tag") or "TECH FACT"
    total = n * D - (n - 1) * X

    scene_files, first_img = [], None
    for i, s in enumerate(scenes):
        img = WORK / ("s%d.jpg" % i)
        if not fetch_image(s["image_prompt"] + ", " + str(spec.get("style", "")), img, spec.get("seed") or random.randint(1, 99999)):
            fallback_image(img, i, accent)
        if first_img is None:
            first_img = img
        anim = s.get("animation") if s.get("animation") in ANIMS else ANIMS[i % 4]
        scene_files.append(make_scene(i, img, anim, grade))

    grad = WORK / "grad.png"
    make_gradient(grad)
    Path("work/sub.ass").write_text(build_ass(scenes, total, accent, tag), encoding="utf-8")
    music = WORK / "music.wav"
    make_music(total, 112 if spec.get("music") == "drive" else 92, spec.get("music") != "bright", str(music), n - 1)

    cmd = ["ffmpeg", "-y"]
    for f in scene_files:
        cmd += ["-i", f]
    cmd += ["-loop", "1", "-i", grad, "-i", music]
    fc, prev = [], "[0:v]"
    for k in range(1, n):
        out = "[x%d]" % k
        fc.append("%s[%d:v]xfade=transition=%s:duration=%.2f:offset=%.2f%s" % (prev, k, TRANS[(k - 1) % len(TRANS)], X, k * (D - X), out))
        prev = out
    fc.append(prev + GRADES[grade] + ",vignette=PI/5,noise=alls=2:allf=t[vg]")
    fc.append("[vg][%d:v]overlay=shortest=1,format=yuv420p[vo]" % n)
    fc.append("[vo]subtitles=work/sub.ass:fontsdir=/usr/share/fonts[vout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "%d:a" % (n + 1), "-t", format(total, ".3f"),
            "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT / "video.mp4"]
    run(cmd)

    th = Path("work/thumb.ass")
    thumb_src = first_img
    if spec.get("thumb_prompt"):
        tb = WORK / "thumbbg.jpg"
        if fetch_image(spec["thumb_prompt"] + ", " + str(spec.get("style", "")) + ", youtube thumbnail, bold, high contrast", tb, (spec.get("seed") or 7) + 11):
            thumb_src = tb
    hl = [l.upper() for l in wrap(esc(spec.get("thumb_text") or spec.get("hook") or scenes[0]["headline"]), 12)]
    w = hl[-1].split(" "); w[-1] = "{\\1c%s}%s" % (ass_color(accent), w[-1]); hl[-1] = " ".join(w)
    body = build_ass([], 5, accent, tag).split("[Events]")[0].replace("Style: Head,%s,92" % FONT, "Style: Head,%s,150" % FONT)
    body += "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    body += "Dialogue: 3,0:00:00.00,0:00:05.00,Head,,0,0,0,,{\\an5\\pos(540,1000)}%s\n" % "\\N".join(hl)
    th.write_text(body, encoding="utf-8")
    vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.12:saturation=1.25,"
          "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.35:t=fill,subtitles=work/thumb.ass:fontsdir=/usr/share/fonts")
    run(["ffmpeg", "-y", "-i", thumb_src, "-vf", vf, "-frames:v", 1, "-q:v", 3, OUT / "thumb.jpg"])
    (OUT / "meta.json").write_text(json.dumps({"title": spec.get("title"), "duration": total, "grade": grade}, ensure_ascii=False))
    print("DONE", total, flush=True)


main()
