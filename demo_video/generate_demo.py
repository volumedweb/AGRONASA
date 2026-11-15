"""Generate demo_video/demo_28s_final.mp4: Playwright capture + edge-tts voiceover + FFmpeg render.

Requires the app on http://127.0.0.1:8000 (start the backend with AGRONASA_OFFLINE_ONLY=1),
plus `pip install playwright edge-tts`, `playwright install chromium` and ffmpeg/ffprobe.
"""
import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

import edge_tts
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
VOICE = HERE / "voice.mp3"
FINAL = HERE / "demo_28s_final.mp4"
URL = "http://127.0.0.1:8000/"
DURATION = 28.0
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WATERMARK = "SI-Assisted Demo | AI Voiceover | ArkByte"
SCRIPT = (
    "Meet AgroNASA by Team ArkByte, an agro-climatic assistant powered by NASA POWER satellite data. "
    "With a single tap on the map, farmers compare regions like Valle, Altiplano, and Tropical Llanos "
    "to see FAO EcoCrop crop viability scores, real-time rainfall alerts, color-coded soil rotation plans, "
    "and LoRaWAN field sensor fusion. Actionable NASA Earth observation for resilient agriculture."
)

SCROLL_JS = """([sel, frac, ms]) => new Promise(done => {
  const c = document.querySelector('#cuerpo');
  const el = c && c.scrollHeight > c.clientHeight + 4 ? c : document.scrollingElement;
  const start = el.scrollTop;
  let target = (el.scrollHeight - el.clientHeight) * frac;
  if (sel) {
    const n = document.querySelector(sel);
    if (n) target = start + n.getBoundingClientRect().top - el.getBoundingClientRect().top - 12;
  }
  target = Math.max(0, Math.min(target, el.scrollHeight - el.clientHeight));
  const t0 = performance.now();
  const step = now => {
    const k = Math.min(1, (now - t0) / ms);
    el.scrollTop = start + (target - start) * (k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
    k < 1 ? requestAnimationFrame(step) : done();
  };
  requestAnimationFrame(step);
})"""


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
         "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def duration(path):
    return float(probe(path)["format"]["duration"])


async def make_voice():
    rate = 5
    for _ in range(4):
        for attempt in range(3):
            try:
                await edge_tts.Communicate(SCRIPT, "en-US-AndrewNeural", rate=f"{rate:+d}%").save(str(VOICE))
                break
            except edge_tts.exceptions.NoAudioReceived:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
        dur = duration(VOICE)
        print(f"voice rate {rate:+d}% -> {dur:.2f}s")
        if 26.0 <= dur <= 27.0:
            break
        rate = round(((1 + rate / 100) * dur / 26.5 - 1) * 100)
    assert dur <= 27.0, f"voice too long: {dur}"
    return dur


async def record():
    shutil.rmtree(RAW, ignore_errors=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(RAW),
            record_video_size={"width": 1920, "height": 1080},
        )
        started = time.monotonic()
        page = await ctx.new_page()
        await page.goto(URL)
        await page.wait_for_selector("#cultivos details.cultivo", timeout=20000)
        t0 = time.monotonic() - 1.0
        lead_in = max(0.0, t0 - started)

        async def until(t):
            await asyncio.sleep(max(0.0, t0 + t - time.monotonic()))

        async def click(sel):
            try:
                await page.click(sel, timeout=1500)
            except Exception:
                await page.evaluate("s => document.querySelector(s)?.click()", sel)

        async def scroll(sel, frac, ms):
            await page.evaluate(SCROLL_JS, [sel, frac, ms])

        # 0-5s: landing, Valle crops
        await until(4.6)
        # 5-10.5s: regions + NASA POWER detail
        await click('button[data-zona="altiplano"]')
        await until(6.7)
        await click('button[data-zona="llanos"]')
        await until(8.7)
        await click("#mas-clima")
        await until(10.7)
        await click("#mas-clima")
        # 10.5-19s: soil + colour-coded rotation
        await until(11.1)
        await click("details.seccion.suelo > summary")
        await until(11.7)
        # the app only renders #plan once some soil data is entered
        for sel, val in (("#f-textura", "franco-arenoso"), ("#f-drenaje", "pobre"), ("#f-n", "bajo")):
            await page.select_option(sel, val)
            await asyncio.sleep(0.25)
        await scroll("#f-ph", 0, 500)
        await page.fill("#f-ph", "5.2")
        await asyncio.sleep(0.25)
        await page.fill("#f-mo", "1.6")
        await scroll('#suelo button[type="submit"]', 0, 500)
        await until(13.9)
        await click('#suelo button[type="submit"]')
        await page.wait_for_function("document.querySelector('#plan')?.children.length > 0", timeout=5000)
        await until(14.5)
        await scroll("#plan", 0, 1100)
        await until(16.1)
        await scroll(None, 1, 2400)
        # 19-28s: IoT LoRaWAN + NASA fusion
        await until(19.0)
        await click("details.seccion.iot > summary")
        await until(19.6)
        await scroll("details.seccion.iot", 0, 700)
        await until(21.2)
        await scroll(None, 0.5, 2400)
        await until(24.4)
        await scroll(None, 1, 2400)
        await until(DURATION + 0.7)
        video = page.video
        await ctx.close()
        path = await video.path()
        await browser.close()
    return Path(path), lead_in


def render(webm, lead_in):
    fade = DURATION - 0.8
    pad = ("0.06*(sin(2*PI*220*t)+0.6*sin(2*PI*277.18*t)+0.5*sin(2*PI*329.63*t))*(1-exp(-t*1.5))")
    fc = (
        f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        f"fps=30,tpad=stop_mode=clone:stop_duration=3,"
        f"drawtext=fontfile={FONT}:text='{WATERMARK}':fontcolor=white:fontsize=24:"
        f"box=1:boxcolor=black@0.55:boxborderw=10:x=w-tw-28:y=h-th-24,format=yuv420p[v];"
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,aformat=channel_layouts=stereo,volume=1.0[vo];"
        f"aevalsrc='{pad}':s=44100:d={DURATION},lowpass=f=900,aformat=channel_layouts=stereo,volume=0.18[bg];"
        f"[vo][bg]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0,"
        f"afade=t=out:st={fade}:d=0.8[a]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{lead_in:.3f}", "-i", str(webm), "-i", str(VOICE),
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", str(DURATION),
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(FINAL)], check=True)


def verify():
    info = probe(FINAL)
    dur = float(info["format"]["duration"])
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    print(json.dumps(info, indent=1))
    assert 27.0 <= dur <= 28.5, dur
    assert (v["width"], v["height"], v["codec_name"]) == (1920, 1080, "h264"), v
    assert a["codec_name"] == "aac", a
    print(f"OK: {FINAL.name} {dur:.2f}s 1920x1080 h264 + aac")


async def main():
    voice_dur = await make_voice()
    webm, lead_in = await record()
    print(f"voice {voice_dur:.2f}s, raw {duration(webm):.2f}s, lead-in trimmed {lead_in:.2f}s")
    render(webm, lead_in)
    verify()
    shutil.rmtree(RAW, ignore_errors=True)
    VOICE.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
