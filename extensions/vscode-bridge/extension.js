const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const path = require('path');
const bridgeVersion = require('./package.json').version;

const bridgeDir = path.join(os.homedir(), '.codex-window-manager');
const requestsDir = path.join(bridgeDir, 'requests');
const resultsDir = path.join(bridgeDir, 'results');
const providersDir = path.join(bridgeDir, 'providers');
const hejuCodexHome = path.join(os.homedir(), '.codex-heju');
const initialCodexHome = process.env.CODEX_HOME;
let lastCleanup = 0;
let remoteStatus = null;
let remoteStatusAt = 0;
let transitioning = false;

function cleanupTransientFiles() {
  const now = Date.now();
  if (now - lastCleanup < 300000) return;
  lastCleanup = now;
  const groups = [
    [bridgeDir, name => name.startsWith('ready-') || name.startsWith('reopen-')],
    [requestsDir, name => name.endsWith('.json')],
    [resultsDir, name => name.endsWith('.json')]
  ];
  for (const [dir, accepts] of groups) {
    try {
      for (const name of fs.readdirSync(dir)) {
        if (!accepts(name)) continue;
        const file = path.join(dir, name);
        try { if (now - fs.statSync(file).mtimeMs > 86400000) fs.unlinkSync(file); } catch {}
      }
    } catch {}
  }
}

function workspacePaths() {
  return (vscode.workspace.workspaceFolders || []).map(folder => path.resolve(folder.uri.fsPath));
}

function workspaceInfo() {
  const paths = workspacePaths();
  const activeFile = vscode.window.activeTextEditor?.document?.uri?.scheme === 'file'
    ? path.resolve(vscode.window.activeTextEditor.document.uri.fsPath)
    : '';
  return {
    pid: process.pid,
    at: Date.now(),
    paths,
    name: vscode.workspace.name || '',
    activeFile,
    remoteName: vscode.env.remoteName || '',
    remoteStatus,
    provider: activeProvider(),
    bridgeVersion
  };
}

async function updateRemoteStatus() {
  if (!vscode.env.remoteName || Date.now() - remoteStatusAt < 4000) return;
  remoteStatusAt = Date.now();
  const root = workspacePaths()[0];
  if (!root) return;
  try { remoteStatus = await vscode.commands.executeCommand('codexRemoteStatus.get', root); }
  catch (error) { remoteStatus = { status: 'monitor_missing', completed: 0, at: Date.now() }; }
}

function token(value) {
  return Buffer.from(value || '').toString('hex');
}

function workspaceIdentity() {
  const paths = workspacePaths();
  return paths.join('|') || vscode.workspace.name || '';
}

function providerMarker() {
  return path.join(providersDir, `${token(workspaceIdentity())}.json`);
}

function savedProvider() {
  try { return JSON.parse(fs.readFileSync(providerMarker(), 'utf8')); }
  catch { return { provider: 'subscription' }; }
}

function activeProvider() {
  const saved = savedProvider();
  const current = process.env.CODEX_HOME ? path.resolve(process.env.CODEX_HOME) : '';
  return saved.provider !== 'subscription' && current === path.resolve(saved.codexHome || hejuCodexHome) ? saved.provider : 'subscription';
}

function applySavedProvider() {
  fs.mkdirSync(providersDir, { recursive: true });
  const saved = savedProvider();
  if (saved.provider && saved.provider !== 'subscription' && saved.codexHome) process.env.CODEX_HOME = path.resolve(saved.codexHome);
  else if (initialCodexHome === undefined) delete process.env.CODEX_HOME;
  else process.env.CODEX_HOME = initialCodexHome;
}

function saveProvider(provider, codexHome) {
  fs.mkdirSync(providersDir, { recursive: true });
  if (provider === 'hejuapi') {
    fs.writeFileSync(providerMarker(), JSON.stringify({ provider, codexHome: path.resolve(codexHome || hejuCodexHome), at: Date.now() }));
  } else if (provider && provider !== 'subscription' && codexHome) {
    fs.writeFileSync(providerMarker(), JSON.stringify({ provider, codexHome: path.resolve(codexHome), at: Date.now() }));
  } else {
    try { fs.unlinkSync(providerMarker()); } catch {}
  }
}

function isInside(file, root) {
  if (!file || !root) return false;
  const relative = path.relative(root, file);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function belongsHere(targetPath) {
  const target = path.resolve(targetPath || '');
  const info = workspaceInfo();
  return info.paths.some(root => root === target)
    || (info.name && info.name === path.basename(target))
    || isInside(info.activeFile, target);
}

function reopenMarker() {
  const info = workspaceInfo();
  const identity = info.paths.join('|') || info.name || info.activeFile;
  return path.join(bridgeDir, `reopen-${token(identity)}.json`);
}

function writeReadyMarkers() {
  const info = workspaceInfo();
  const markers = info.paths.map(root => `ready-${token(root)}.json`);
  if (info.name) markers.push(`ready-name-${token(info.name)}.json`);
  if (info.activeFile) markers.push(`ready-active-${process.pid}.json`);
  if (!markers.length) markers.push(`ready-empty-${process.pid}.json`);
  for (const marker of new Set(markers)) {
    fs.writeFileSync(path.join(bridgeDir, marker), JSON.stringify(info));
  }
}

async function processRequests() {
  if (transitioning) return;
  fs.mkdirSync(requestsDir, { recursive: true });
  fs.mkdirSync(resultsDir, { recursive: true });
  cleanupTransientFiles();
  await updateRemoteStatus();
  writeReadyMarkers();
  for (const filename of fs.readdirSync(requestsDir).filter(name => name.endsWith('.json'))) {
    const requestFile = path.join(requestsDir, filename);
    let request;
    try { request = JSON.parse(fs.readFileSync(requestFile, 'utf8')); } catch { continue; }
    if (!belongsHere(request.targetPath)) continue;
    try {
      if (request.action === 'ping') {
        fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: true, at: Date.now() }));
        fs.unlinkSync(requestFile);
        continue;
      }
      if (request.action === 'reloadWindow') {
        fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: true, at: Date.now() }));
        fs.unlinkSync(requestFile);
        setTimeout(() => vscode.commands.executeCommand('workbench.action.reloadWindow'), 250);
        continue;
      }
      if (request.action === 'openConversation') {
        if (!request.conversationId) throw new Error('缺少对话 ID');
        const uri = vscode.Uri.parse(`openai-codex://route/local/${request.conversationId}`);
        await vscode.commands.executeCommand('vscode.openWith', uri, 'chatgpt.conversationEditor');
        fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: true, at: Date.now() }));
        fs.unlinkSync(requestFile);
        continue;
      }
      if (request.action === 'switchProvider') {
        const provider = request.provider && request.provider !== 'subscription' ? request.provider : 'subscription';
        if (provider !== activeProvider()) {
          const requestedHome = path.resolve(request.codexHome || hejuCodexHome);
          const allowedHome = requestedHome === path.resolve(hejuCodexHome) || requestedHome.startsWith(path.join(os.homedir(), '.codex-providers') + path.sep);
          if (provider !== 'subscription' && !allowedHome) throw new Error('API 配置目录不在允许范围内');
          saveProvider(provider, requestedHome);
          fs.writeFileSync(reopenMarker(), JSON.stringify({ profileName: request.profileName, at: Date.now() }));
          transitioning = true;
          setTimeout(() => vscode.commands.executeCommand('workbench.action.restartExtensionHost'), 250);
          return;
        }
        fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: true, profileName: request.profileName, provider, at: Date.now() }));
        fs.unlinkSync(requestFile);
        setTimeout(() => vscode.commands.executeCommand('chatgpt.openSidebar'), 500);
        continue;
      }
      if (activeProvider() !== 'subscription') {
        saveProvider('subscription');
        fs.writeFileSync(reopenMarker(), JSON.stringify({ profileName: request.profileName, at: Date.now() }));
        transitioning = true;
        setTimeout(() => vscode.commands.executeCommand('workbench.action.restartExtensionHost'), 250);
        return;
      }
      await vscode.commands.executeCommand('codex-switch.profile.activate', request.profileId);
      fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: true, profileName: request.profileName, at: Date.now() }));
      fs.unlinkSync(requestFile);
      fs.writeFileSync(reopenMarker(), JSON.stringify({ profileName: request.profileName, at: Date.now() }));
      await new Promise(resolve => setTimeout(resolve, 500));
      await vscode.commands.executeCommand('workbench.action.restartExtensionHost');
    } catch (error) {
      fs.writeFileSync(path.join(resultsDir, filename), JSON.stringify({ ok: false, error: String(error), at: Date.now() }));
      fs.unlinkSync(requestFile);
    }
  }
}

async function reopenCodex() {
  const marker = reopenMarker();
  if (!fs.existsSync(marker)) return;
  try { fs.unlinkSync(marker); } catch {}
  setTimeout(() => vscode.commands.executeCommand('chatgpt.openSidebar'), 1200);
}

function activate(context) {
  applySavedProvider();
  fs.mkdirSync(requestsDir, { recursive: true });
  const timer = setInterval(() => processRequests().catch(() => {}), 1000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
  processRequests().catch(() => {});
  reopenCodex().catch(() => {});
}

function deactivate() {}
module.exports = { activate, deactivate };
