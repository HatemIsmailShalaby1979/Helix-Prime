/**
 * Capture Helix_Codex_5Min_Animated.html as a frame sequence, for the MP4 export.
 *
 * Drives the real film in headless Chrome over CDP and records a variable-rate
 * JPEG sequence plus per-frame timestamps. The film is loaded with `#auto`, which
 * skips the start gate and plays silently - the narration is muxed separately
 * from audio/beat-NNN.mp3 by export_video.py, which is both higher quality and
 * deterministic compared with trying to capture browser audio.
 *
 * Usage: node capture_frames.mjs <outDir> [maxSeconds] [quality]
 * Writes: <outDir>/frame-000001.jpg ... and <outDir>/frames.json
 */

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFile, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

process.env.UV_THREADPOOL_SIZE = process.env.UV_THREADPOOL_SIZE || '8';

const CHROME = process.env.CHROME ||
  'C:/Program Files/Google/Chrome/Application/chrome.exe';
const FILM = process.env.FILM ||
  'file:///E:/Helix-Prime/marketing/helix-codex-deck/video/Helix_Codex_5Min_Animated.html';
const PORT = Number(process.env.PORT || 9411);

const outDir = resolve(process.argv[2] || 'frames');
const maxSeconds = Number(process.argv[3] || 0);   // 0 = until the film ends
const quality = Number(process.argv[4] || 78);

mkdirSync(outDir, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), 'hx-cap-'));

const chrome = spawn(CHROME, [
  '--headless=new',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check',
  '--hide-scrollbars', '--mute-audio',
  '--window-size=1920,1080',
  '--autoplay-policy=no-user-gesture-required',
  '--disable-background-timer-throttling',
  '--disable-renderer-backgrounding',
  FILM + '#auto',
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function targetWs() {
  for (let i = 0; i < 80; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const p = (await r.json()).find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (p) return p.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error('no devtools target');
}

const ws = new WebSocket(await targetWs());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let id = 0;
const pending = new Map();
const stamps = [];
let n = 0;

function send(method, params = {}) {
  const mid = ++id;
  return new Promise(res => { pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
}
async function ev(expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true });
  const res = r.result || {};
  return res.result ? res.result.value : undefined;
}

/* Frames are written asynchronously: a blocking write here delays the ack and
   throttles the screencast (measured: 19 fps sync vs 35 fps async). */
const writes = [];

ws.onmessage = evt => {
  const m = JSON.parse(evt.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
  if (m.method === 'Page.screencastFrame') {
    const { data, metadata, sessionId } = m.params;
    n += 1;
    writes.push(new Promise(res => {
      writeFile(join(outDir, `frame-${String(n).padStart(6, '0')}.jpg`),
        Buffer.from(data, 'base64'), () => res());
    }));
    stamps.push(metadata.timestamp);
    send('Page.screencastFrameAck', { sessionId });
  }
};

await send('Page.enable');
await send('Runtime.enable');

let ready = false;
for (let i = 0; i < 80; i++) {
  await sleep(250);
  if ((await ev("document.readyState + '|' + (!!document.getElementById('endcard'))")) === 'complete|true') { ready = true; break; }
}
if (!ready) { console.error('FATAL: the film never became ready'); ws.close(); chrome.kill(); process.exit(2); }

await sleep(900);

const t0 = await ev("document.getElementById('tc').textContent");
await send('Page.startScreencast', { format: 'jpeg', quality, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });

/* Let frame one land while the film is still held at 0:00, then start playback.
   Starting the capture before the clock moves is what keeps the frames and the
   narration bed in sync - otherwise the first frame is already a second in. */
for (let i = 0; i < 40 && n < 1; i++) await sleep(100);
await ev("window.__film.play()");

const started = Date.now();
let done = false;
let sawEndcard = false;
while (!done) {
  await sleep(500);
  const ended = await ev("document.getElementById('endcard').classList.contains('on')");
  const secs = (Date.now() - started) / 1000;
  if (ended === true) { done = true; sawEndcard = true; }
  if (maxSeconds > 0 && secs >= maxSeconds) done = true;
  if (secs > 420) { console.error('WARN: capture exceeded 7 minutes, stopping'); done = true; }
  if (n > 0 && n % 300 === 0) console.error(`  ... ${n} frames`);
}

await send('Page.stopScreencast');
const t1 = await ev("document.getElementById('tc').textContent");
const elapsed = await ev("window.__film.elapsed()");
await Promise.all(writes);

const span = stamps.length ? stamps[stamps.length - 1] - stamps[0] : 0;
writeFileSync(join(outDir, 'frames.json'), JSON.stringify({
  count: stamps.length,
  span,
  elapsed,
  sawEndcard,
  clockStart: t0,
  clockEnd: t1,
  timestamps: stamps,
}, null, 1));

console.log(`capture: maxSeconds=${maxSeconds || 'whole film'} quality=${quality}`);
console.log(`frames: ${stamps.length} over ${span.toFixed(2)}s (${(stamps.length / Math.max(0.001, span)).toFixed(1)} fps)`);
console.log(`clock: ${t0} -> ${t1}   film elapsed ${Number(elapsed).toFixed(2)}s`);
console.log(`film played to the end: ${sawEndcard}`);
console.log(`sync: capture span ${span.toFixed(2)}s vs film ${Number(elapsed).toFixed(2)}s ` +
  `=> ${(span - Number(elapsed)).toFixed(2)}s drift`);
console.log(`wrote ${outDir}/frames.json`);

ws.close();
chrome.kill();
