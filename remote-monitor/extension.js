const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const path = require('path');

const sessionRoot = path.join(os.homedir(), '.codex', 'sessions');
const headers = new Map();
const streams = new Map();
let lastIndexAt = 0;
let latestByCwd = new Map();

function walk(dir, output = []) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return output; }
  for (const entry of entries) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file, output);
    else if (entry.isFile() && entry.name.endsWith('.jsonl')) output.push(file);
  }
  return output;
}

function firstLine(file) {
  const fd = fs.openSync(file, 'r');
  try {
    const buffer = Buffer.alloc(65536);
    const length = fs.readSync(fd, buffer, 0, buffer.length, 0);
    const end = buffer.indexOf(10, 0);
    return buffer.subarray(0, end >= 0 && end < length ? end : length).toString('utf8');
  } finally { fs.closeSync(fd); }
}

function buildIndex() {
  const now = Date.now();
  if (now - lastIndexAt < 5000) return;
  lastIndexAt = now;
  const next = new Map();
  for (const file of walk(sessionRoot)) {
    let stat;
    try { stat = fs.statSync(file); } catch { continue; }
    let header = headers.get(file);
    if (!header) {
      try {
        const payload = JSON.parse(firstLine(file)).payload || {};
        header = { cwd: payload.cwd, source: payload.source, originator: payload.originator };
        headers.set(file, header);
      } catch { continue; }
    }
    if (!header.cwd || (header.source !== 'vscode' && header.originator !== 'codex_vscode')) continue;
    const previous = next.get(header.cwd);
    if (!previous || stat.mtimeMs > previous.stat.mtimeMs) next.set(header.cwd, { file, stat });
  }
  latestByCwd = next;
}

function parseIncremental(item) {
  const { file } = item;
  let stat;
  try { stat = fs.statSync(file); } catch { return null; }
  let state = streams.get(file);
  if (!state || state.ino !== stat.ino || stat.size < state.offset) {
    state = { ino: stat.ino, offset: 0, carry: '', line: 0, started: 0, done: 0, completedAt: 0 };
  }
  if (stat.size > state.offset) {
    const fd = fs.openSync(file, 'r');
    try {
      const length = stat.size - state.offset;
      const buffer = Buffer.alloc(length);
      fs.readSync(fd, buffer, 0, length, state.offset);
      state.offset = stat.size;
      const chunks = (state.carry + buffer.toString('utf8')).split('\n');
      state.carry = chunks.pop() || '';
      for (const line of chunks) {
        if (!line) continue;
        let payload;
        try { payload = (JSON.parse(line).payload || {}); } catch { continue; }
        state.line += 1;
        if (payload.type === 'task_started') state.started = state.line;
        if (payload.type === 'task_complete') {
          state.done = state.line;
          state.completedAt = payload.completed_at || stat.mtimeMs / 1000;
        }
      }
    } finally { fs.closeSync(fd); }
  }
  streams.set(file, state);
  return state;
}

function statusFor(workspacePath) {
  buildIndex();
  const item = latestByCwd.get(path.resolve(workspacePath || ''));
  if (!item) return { status: 'no_session', completed: 0, at: Date.now() };
  const state = parseIncremental(item);
  if (!state) return { status: 'unknown', completed: 0, at: Date.now() };
  return {
    status: state.started > state.done ? 'running' : (state.done ? 'complete' : 'idle'),
    completed: state.done ? state.completedAt : 0,
    at: Date.now()
  };
}

function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('codexRemoteStatus.get', statusFor));
}

function deactivate() {}
module.exports = { activate, deactivate };
