#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';
import { createServer } from 'vite';

const root = resolve(import.meta.dirname, '..');
const lock = resolve(root, 'node_modules', '.blender-lab-sync.pid');
const syncEveryMs = 15_000;
let server;
let ownsLock = false;
let stopping = false;
let syncing = false;

function pidIsAlive(pid) {
  if (!Number.isInteger(pid) || pid < 1) return false;
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function acquireLock() {
  if (existsSync(lock)) {
    const pid = Number(readFileSync(lock, 'utf8').trim());
    if (pidIsAlive(pid)) {
      console.log(`[Blender Lab] GitHub sync is already running (PID ${pid}).`);
      return false;
    }
    unlinkSync(lock);
  }
  writeFileSync(lock, `${process.pid}\n`, { flag: 'wx' });
  ownsLock = true;
  return true;
}

function git(args) {
  return spawnSync('git', args, { cwd: root, encoding: 'utf8', windowsHide: true });
}

async function startVite() {
  try {
    server = await createServer({
      configFile: resolve(root, 'vite.config.js'),
      root,
      server: { host: '127.0.0.1', port: 5173, strictPort: true },
    });
    await server.listen();
    server.printUrls();
  } catch (error) {
    await server?.close();
    server = undefined;
    if (error?.code === 'EADDRINUSE') {
      console.log('[Blender Lab] Port 5173 already has a server; GitHub sync will still run.');
      return;
    }
    throw error;
  }
}

function syncMain() {
  if (syncing || stopping) return;
  syncing = true;
  const before = git(['rev-parse', 'HEAD']);
  const pull = git(['pull', '--ff-only', '--quiet', 'origin', 'main']);
  const after = git(['rev-parse', 'HEAD']);
  syncing = false;
  if (pull.error || pull.status !== 0) {
    const detail = (pull.stderr || pull.error?.message || 'Git pull failed').trim();
    console.error(`[Blender Lab] Could not sync GitHub main: ${detail}`);
    return;
  }
  if (before.status === 0 && after.status === 0 && before.stdout.trim() !== after.stdout.trim()) {
    console.log('[Blender Lab] Updated from GitHub main. The browser will reload changed models.');
  }
}

async function stop() {
  if (stopping) return;
  stopping = true;
  await server?.close();
  if (ownsLock && existsSync(lock) && Number(readFileSync(lock, 'utf8').trim()) === process.pid) unlinkSync(lock);
}

if (!acquireLock()) process.exit(0);
process.on('SIGINT', () => { void stop().finally(() => process.exit(0)); });
process.on('SIGTERM', () => { void stop().finally(() => process.exit(0)); });
process.on('exit', () => {
  if (ownsLock && existsSync(lock) && Number(readFileSync(lock, 'utf8').trim()) === process.pid) unlinkSync(lock);
});

try {
  await startVite();
  console.log('[Blender Lab] Watching GitHub main every 15 seconds; keep this window open.');
  syncMain();
  const timer = setInterval(syncMain, syncEveryMs);
} catch (error) {
  console.error(`[Blender Lab] Startup failed: ${error.message}`);
  await stop();
  process.exitCode = 1;
}
