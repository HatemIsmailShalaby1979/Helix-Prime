import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const FILE = 'file:///E:/Helix-Prime/marketing/helix-codex-deck/video/Helix_Codex_5Min_Animated.html';
const PORT = Number(process.env.PORT || 9333);
const HASH = process.argv[2] || '';
const PACK = process.env.PACK === '1';      // true => audio/beat-NNN.mp3 exists
const LISTEN_MS = Number(process.env.LISTEN_MS || 23000);

const profile = mkdtempSync(join(tmpdir(), 'hx-audio-'));
const chrome = spawn(CHROME, [
  '--headless=new',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--hide-scrollbars',
  '--window-size=1920,1080',
  '--autoplay-policy=no-user-gesture-required',
  '--allow-file-access-from-files',
  FILE + HASH,
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function targetWs() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const page = (await r.json()).find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error('no devtools target');
}

const ws = new WebSocket(await targetWs());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let id = 0;
const pending = new Map();
const exceptions = [];
const mediaErrs = [];   // urls that failed to load
const voiceReqs = [];   // every audio/beat-NNN.mp3 request the film made

ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails;
    exceptions.push((d.exception && d.exception.description) || d.text);
  }
  if (m.method === 'Network.requestWillBeSent') {
    const u = m.params.request.url;
    if (u.indexOf('audio/beat-') !== -1) voiceReqs.push(u.split('/').pop());
  }
  if (m.method === 'Log.entryAdded') {
    const e = m.params.entry;
    if (e.level === 'error' && (e.url || '').indexOf('audio/beat-') !== -1) mediaErrs.push(e.url);
  }
};

const send = (method, params = {}) => {
  const mid = ++id;
  return new Promise(res => { pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
};
async function ev(expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  const res = r.result || {};
  if (res.exceptionDetails) return { __err: res.exceptionDetails.text };
  return res.result ? res.result.value : undefined;
}

await send('Runtime.enable');
await send('Log.enable');
await send('Page.enable');
await send('Network.enable');

/* Wait for the film to actually be on the page — a cold Chrome profile can take
   several seconds, and probing early silently returns undefined for every element. */
let ready = false;
for (let i = 0; i < 80; i++) {
  await sleep(250);
  const st = await ev("document.readyState + '|' + (!!document.getElementById('gate')) + '|' + (!!document.getElementById('bSound'))");
  if (st === 'complete|true|true') { ready = true; break; }
}
if (!ready) { console.log('FATAL: film never became ready'); ws.close(); chrome.kill(); process.exit(2); }
await sleep(600);

const results = [];
const check = (name, pass, detail) => results.push({ name, pass: !!pass, detail });

const attempts = async () => voiceReqs.length;

if (!HASH) {
  check('T1 start gate visible at boot',
    /\bon\b/.test(await ev("document.getElementById('gate').className")) &&
    (await ev("getComputedStyle(document.getElementById('gate')).display")) === 'grid',
    `display=${await ev("getComputedStyle(document.getElementById('gate')).display")}`);

  check('T1b sound starts OFF', /\boff\b/.test(await ev("document.getElementById('bSound').className")),
    await ev("document.getElementById('bSound').className"));

  await ev("document.getElementById('gateSound').click()");
  await sleep(1400);
  check('T2 narration button hides gate', /\bgone\b/.test(await ev("document.getElementById('gate').className")),
    await ev("document.getElementById('gate').className"));
  check('T2b sound button ON', /\bon\b/.test(await ev("document.getElementById('bSound').className")),
    await ev("document.getElementById('bSound').className"));

  const tc1 = await ev("document.getElementById('tc').textContent");
  await sleep(1600);
  const tc2 = await ev("document.getElementById('tc').textContent");
  check('T2c clock advancing', tc1 !== tc2, `${JSON.stringify(tc1)} -> ${JSON.stringify(tc2)}`);

  const a1 = await attempts();
  check('T3 voice track requested', a1 >= 1, `${a1} request(s)`);

  await ev("window.dispatchEvent(new KeyboardEvent('keydown',{key:'m'}))");
  await sleep(300);
  const off = await ev("document.getElementById('bSound').className");
  await ev("window.dispatchEvent(new KeyboardEvent('keydown',{key:'m'}))");
  await sleep(300);
  const on = await ev("document.getElementById('bSound').className");
  check('T4 M mutes', /\boff\b/.test(off), off);
  check('T4b M unmutes', /\bon\b/.test(on), on);

  const before = exceptions.length;
  await ev("document.getElementById('bNext').click()");
  await sleep(400);
  await ev("document.getElementById('bPlay').click()");
  await sleep(1000);
  check('T5 scene change + chime, no exception', exceptions.length === before,
    exceptions.slice(before).join(' | ') || 'clean');

  await ev("window.dispatchEvent(new KeyboardEvent('keydown',{key:'m'}))");
  await ev("document.getElementById('bRestart').click()");
  await sleep(900);
  check('T6 restart preserves mute state', /\boff\b/.test(await ev("document.getElementById('bSound').className")),
    await ev("document.getElementById('bSound').className"));

  /* unmute and listen across several beats to prove the fallback latch */
  await ev("window.dispatchEvent(new KeyboardEvent('keydown',{key:'m'}))");
  const a2 = await attempts();
  await sleep(LISTEN_MS);
  const a3 = await attempts();
  const beatsSeen = await ev("document.getElementById('tc').textContent");

  if (PACK) {
    check('T7 pack present: one clip per beat', a3 > a2,
      `${a2} -> ${a3} clips (at ${beatsSeen}): ${voiceReqs.join(' ')}`);
    check('T7b pack present: no missing-file errors', mediaErrs.length === 0,
      mediaErrs.length ? mediaErrs.slice(0, 3).join(', ') : 'none');
  } else {
    check('T7 pack absent: latches to synthesis after first miss', a3 === a2,
      `${a2} -> ${a3} requests (at ${beatsSeen})`);
    check('T7b pack absent: miss reported once', mediaErrs.length === 1,
      `${mediaErrs.length} error(s)`);
  }
} else {
  const want = /t=(\d+)/.exec(HASH);
  const mmss = want
    ? String(Math.floor(Number(want[1]) / 60)).padStart(2, '0') + ':' + String(Number(want[1]) % 60).padStart(2, '0')
    : null;
  check('T1 deep link skips the gate',
    !/\bon\b/.test(await ev("document.getElementById('gate').className")) &&
    (await ev("getComputedStyle(document.getElementById('gate')).display")) === 'none',
    `display=${await ev("getComputedStyle(document.getElementById('gate')).display")}`);

  const c1 = await ev("document.getElementById('tc').textContent");
  await sleep(1500);
  const c2 = await ev("document.getElementById('tc').textContent");
  check('T1b deep link holds at the requested time',
    (!mmss || c1.indexOf(mmss) === 0) && c1 === c2,
    `${JSON.stringify(c1)} -> ${JSON.stringify(c2)}${mmss ? ' (wanted ' + mmss + ')' : ''}`);
}

check('T8 zero uncaught exceptions', exceptions.length === 0, exceptions.slice(0, 4).join(' | ') || 'none');

let failed = 0;
for (const r of results) {
  if (!r.pass) failed++;
  console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name.padEnd(46, ' ')} ${r.detail}`);
}
console.log(`\n${results.length - failed}/${results.length} passed  [${PACK ? 'pack' : 'no-pack'}${HASH ? ' · ' + HASH : ''}]`);

ws.close();
chrome.kill();
process.exit(failed ? 1 : 0);
