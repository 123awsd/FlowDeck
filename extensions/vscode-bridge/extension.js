const vscode = require('vscode');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const bridgeVersion = require('./package.json').version;
const bridgeDir = path.join(os.homedir(), '.codex-window-manager');
const requestsDir = path.join(bridgeDir, 'requests');
const resultsDir = path.join(bridgeDir, 'results');
const routesDir = path.join(bridgeDir, 'routes');
const hostsDir = path.join(bridgeDir, 'hosts');
const transactionsDir = path.join(bridgeDir, 'transactions');
const defaultCodexHome = path.join(os.homedir(), '.codex');
let lastCleanup = 0, remoteStatus = null, remoteStatusAt = 0, transitioning = false;

function atomicJson(target, value) {
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = `${target}.tmp.${process.pid}`;
  fs.writeFileSync(temporary, JSON.stringify(value), { mode: 0o600 });
  fs.renameSync(temporary, target);
}
function token(value) { return Buffer.from(value || '').toString('hex'); }
function workspacePaths() { return (vscode.workspace.workspaceFolders || []).map(folder => path.resolve(folder.uri.fsPath)); }
function workspaceFingerprint() {
  const identity = JSON.stringify({ paths: workspacePaths(), name: vscode.workspace.name || '', remote: vscode.env.remoteName || '' });
  return crypto.createHash('sha256').update(identity).digest('hex').slice(0, 20);
}
function routeFile() { return path.join(routesDir, `${token(vscode.env.sessionId)}.json`); }
function savedRoute() {
  try {
    const route = JSON.parse(fs.readFileSync(routeFile(), 'utf8'));
    if (route.workspaceFingerprint === workspaceFingerprint()) return route;
  } catch {}
  return { provider: 'subscription', codexHome: '', providerName: '' };
}
function saveRoute(provider, codexHome, providerName) {
  const value = { sessionId: vscode.env.sessionId, workspaceFingerprint: workspaceFingerprint(),
    provider: provider && provider !== 'subscription' ? provider : 'subscription', providerName: providerName || '',
    codexHome: provider && provider !== 'subscription' ? path.resolve(codexHome) : '', at: Date.now() };
  atomicJson(routeFile(), value); return value;
}
function publishHostRoute(route = savedRoute()) {
  atomicJson(path.join(hostsDir, `${process.pid}.json`), { ...route, pid: process.pid, at: Date.now() });
}
function publishLaunchTicket(route) {
  const target = path.join(bridgeDir, 'pending-launch.json');
  try {
    const current = JSON.parse(fs.readFileSync(target, 'utf8'));
    if (Date.now() - current.at < 15000) throw new Error('另一个窗口正在切换账号，请等待它完成');
  } catch (error) {
    if (String(error).includes('另一个窗口')) throw error;
  }
  atomicJson(target, { provider: route.provider, codexHome: route.codexHome || '', sessionId: route.sessionId, at: Date.now() });
}
function childProcesses() {
  const children = [];
  try {
    for (const name of fs.readdirSync('/proc')) {
      if (!/^\d+$/.test(name)) continue;
      const status = fs.readFileSync(path.join('/proc', name, 'status'), 'utf8');
      const parent = /^PPid:\s+(\d+)/m.exec(status);
      if (!parent || Number(parent[1]) !== process.pid) continue;
      const command = fs.readFileSync(path.join('/proc', name, 'cmdline'), 'utf8').replaceAll('\0', ' ');
      if (!command.includes('openai.chatgpt') || !command.includes('codex') || !command.includes('app-server')) continue;
      let codexHome = '';
      try { codexHome = (fs.readFileSync(path.join('/proc', name, 'environ'), 'utf8').split('\0').find(v => v.startsWith('CODEX_HOME=')) || '').slice(11); } catch {}
      children.push({ pid: Number(name), codexHome });
    }
  } catch {}
  return children;
}
function expectedHome(route) { return route.provider === 'subscription' ? '' : path.resolve(route.codexHome || ''); }
function matchingChild(route) {
  const expected = expectedHome(route);
  return childProcesses().find(child => expected ? path.resolve(child.codexHome || '/') === expected : !child.codexHome);
}
function configSummary(route) {
  const root = route.provider === 'subscription' ? defaultCodexHome : route.codexHome;
  try {
    const config = fs.readFileSync(path.join(root, 'config.toml'), 'utf8');
    const read = key => new RegExp(`^${key}\\s*=\\s*["']([^"']+)["']`, 'm').exec(config)?.[1] || '';
    return { model: read('model'), modelProvider: read('model_provider') };
  } catch { return { model: '', modelProvider: '' }; }
}
async function restartAndVerify(route) {
  publishHostRoute(route);
  for (const child of childProcesses()) { try { process.kill(child.pid, 'SIGTERM'); } catch {} }
  try { await vscode.commands.executeCommand('chatgpt.openSidebar'); } catch {}
  const deadline = Date.now() + 18000;
  while (Date.now() < deadline) {
    const child = matchingChild(route);
    if (child) return { childPid: child.pid, actualCodexHome: child.codexHome || '', ...configSummary(route) };
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  throw new Error('Codex 子进程未在限定时间内以目标账号来源启动');
}
async function waitForVerifiedChild(route, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const child = matchingChild(route);
    if (child) return { childPid: child.pid, actualCodexHome: child.codexHome || '', ...configSummary(route) };
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  return null;
}
function workspaceInfo() {
  const paths = workspacePaths();
  const activeFile = vscode.window.activeTextEditor?.document?.uri?.scheme === 'file' ? path.resolve(vscode.window.activeTextEditor.document.uri.fsPath) : '';
  const route = savedRoute(), child = matchingChild(route), verified = Boolean(child);
  return { pid: process.pid, at: Date.now(), sessionId: vscode.env.sessionId, workspaceFingerprint: workspaceFingerprint(), paths,
    name: vscode.workspace.name || '', activeFile, focused: vscode.window.state.focused, remoteName: vscode.env.remoteName || '', remoteStatus,
    provider: verified ? route.provider : 'unknown', providerName: verified ? route.providerName : '', codexHome: verified ? (child.codexHome || '') : '',
    childPid: child?.pid || 0, verified, bridgeVersion };
}
function writeReadyMarkers() {
  const info = workspaceInfo();
  const markers = info.paths.map(root => `ready-${token(root)}-${process.pid}.json`);
  if (info.activeFile) markers.push(`ready-active-${process.pid}.json`);
  if (!markers.length) markers.push(`ready-empty-${process.pid}.json`);
  for (const marker of new Set(markers)) atomicJson(path.join(bridgeDir, marker), info);
}
function isInside(file, root) {
  if (!file || !root) return false;
  const relative = path.relative(root, file);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}
function belongsHere(request) {
  if (request.targetBridgePid && Number(request.targetBridgePid) !== process.pid) return false;
  const target = path.resolve(request.targetPath || '');
  return workspacePaths().some(root => root === target) || isInside(vscode.window.activeTextEditor?.document?.uri?.fsPath || '', target);
}
async function updateRemoteStatus() {
  if (!vscode.env.remoteName || Date.now() - remoteStatusAt < 4000) return;
  remoteStatusAt = Date.now(); const root = workspacePaths()[0]; if (!root) return;
  try { remoteStatus = await vscode.commands.executeCommand('codexRemoteStatus.get', root); }
  catch { remoteStatus = { status: 'monitor_missing', completed: 0, at: Date.now() }; }
}
function cleanup() {
  const now = Date.now(); if (now - lastCleanup < 300000) return; lastCleanup = now;
  for (const [dir, prefix, maxAge] of [[bridgeDir, 'ready-', 86400000], [requestsDir, '', 86400000], [resultsDir, '', 86400000], [hostsDir, '', 86400000], [transactionsDir, '', 86400000], [routesDir, '', 604800000]]) {
    try { for (const name of fs.readdirSync(dir)) { if (prefix && !name.startsWith(prefix)) continue; const file = path.join(dir, name); try { if (now - fs.statSync(file).mtimeMs > maxAge) fs.unlinkSync(file); } catch {} } } catch {}
  }
}
function result(request, value) { atomicJson(path.join(resultsDir, path.basename(request.__filename)), value); try { fs.unlinkSync(request.__path); } catch {} }
function transactionFile() { return path.join(transactionsDir, `${token(vscode.env.sessionId)}.json`); }
async function resumeTransaction() {
  let file = transactionFile(), transaction;
  try { transaction = JSON.parse(fs.readFileSync(file, 'utf8')); } catch {
    try {
      const matches = fs.readdirSync(transactionsDir).map(name => path.join(transactionsDir, name)).map(candidate => {
        try { return [candidate, JSON.parse(fs.readFileSync(candidate, 'utf8'))]; } catch { return null; }
      }).filter(Boolean).filter(([, value]) => value.workspaceFingerprint === workspaceFingerprint()).sort((a, b) => b[1].at - a[1].at);
      if (!matches.length) return; [file, transaction] = matches[0];
    } catch { return; }
  }
  if (transaction.workspaceFingerprint !== workspaceFingerprint()) return;
  const verified = await waitForVerifiedChild(transaction.route);
  if (verified) {
    saveRoute(transaction.route.provider, transaction.route.codexHome, transaction.route.providerName);
    atomicJson(path.join(resultsDir, transaction.resultName), { ok: true, phase: 'verified', provider: transaction.route.provider,
      profileName: transaction.route.providerName, sessionId: vscode.env.sessionId, workspaceFingerprint: workspaceFingerprint(), ...verified, at: Date.now() });
    try { fs.unlinkSync(file); } catch {}
    return;
  }
  if ((transaction.attempts || 0) < 1) {
    transaction.attempts = (transaction.attempts || 0) + 1; transaction.at = Date.now();
    atomicJson(file, transaction); saveRoute(transaction.route.provider, transaction.route.codexHome, transaction.route.providerName); publishHostRoute(transaction.route); publishLaunchTicket(transaction.route);
    setTimeout(() => vscode.commands.executeCommand('workbench.action.restartExtensionHost'), 250);
    return;
  }
  saveRoute(transaction.previous.provider, transaction.previous.codexHome, transaction.previous.providerName);
  publishHostRoute(transaction.previous);
  atomicJson(path.join(resultsDir, transaction.resultName), { ok: false, phase: 'rolled_back', error: 'Codex 子进程未按目标账号来源启动，已恢复原路由', at: Date.now() });
  try { fs.unlinkSync(file); } catch {}
}
async function processRequests() {
  if (transitioning) return;
  cleanup(); await updateRemoteStatus(); publishHostRoute(); writeReadyMarkers(); fs.mkdirSync(requestsDir, { recursive: true, mode: 0o700 });
  for (const filename of fs.readdirSync(requestsDir).filter(name => name.endsWith('.json'))) {
    const requestPath = path.join(requestsDir, filename); let request;
    try { request = { ...JSON.parse(fs.readFileSync(requestPath, 'utf8')), __filename: filename, __path: requestPath }; } catch { continue; }
    if (!belongsHere(request)) continue;
    try {
      if (request.action === 'ping') { result(request, { ok: true, at: Date.now() }); continue; }
      if (request.action === 'reloadWindow') { result(request, { ok: true, at: Date.now() }); setTimeout(() => vscode.commands.executeCommand('workbench.action.reloadWindow'), 250); return; }
      if (request.action === 'openConversation') {
        if (!request.conversationId) throw new Error('缺少对话 ID');
        await vscode.commands.executeCommand('vscode.openWith', vscode.Uri.parse(`openai-codex://route/local/${request.conversationId}`), 'chatgpt.conversationEditor');
        result(request, { ok: true, at: Date.now() }); continue;
      }
      if (!['switchProvider', 'switchAccount'].includes(request.action)) continue;
      transitioning = true;
      const provider = request.action === 'switchProvider' ? request.provider : 'subscription';
      const home = provider === 'subscription' ? '' : path.resolve(request.codexHome || '');
      const allowed = home === path.join(os.homedir(), '.codex-heju') || home.startsWith(path.join(os.homedir(), '.codex-providers') + path.sep);
      if (provider !== 'subscription' && !allowed) throw new Error('API 配置目录不在允许范围内');
      if (provider === 'subscription' && request.profileId) await vscode.commands.executeCommand('codex-switch.profile.activate', request.profileId);
      const previous = savedRoute(), route = saveRoute(provider, home, request.profileName);
      atomicJson(transactionFile(), { workspaceFingerprint: workspaceFingerprint(), resultName: filename, previous, route, attempts: 0, at: Date.now() });
      try { fs.unlinkSync(requestPath); } catch {}
      publishHostRoute(route); publishLaunchTicket(route);
      setTimeout(() => vscode.commands.executeCommand('workbench.action.restartExtensionHost'), 250);
      return;
    } catch (error) { transitioning = false; result(request, { ok: false, phase: 'rolled_back', error: String(error), at: Date.now() }); }
  }
}
function activate(context) {
  fs.mkdirSync(bridgeDir, { recursive: true, mode: 0o700 }); publishHostRoute(); writeReadyMarkers();
  const timer = setInterval(() => processRequests().catch(() => {}), 1000); context.subscriptions.push({ dispose: () => clearInterval(timer) });
  setTimeout(() => resumeTransaction().catch(() => {}), 900); processRequests().catch(() => {});
}
function deactivate() {}
module.exports = { activate, deactivate };
