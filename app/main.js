const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

const PORT = Number(process.env.FM07_PORT || 47810);
const PYTHON = process.env.FM07_PYTHON || 'python';
const BACKEND = path.join(__dirname, '..', 'backend', 'server.py');

let backend = null;

function startBackend() {
  return new Promise((resolve, reject) => {
    // --watch-stdin: il backend si chiude da solo quando l'editor termina
    // Versione impacchettata: backend.exe (PyInstaller) dentro resources/backend; in sviluppo: python server.py
    const args = ['--port', String(PORT), '--watch-stdin'];
    const exe = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'backend.exe') : PYTHON;
    const cwd = app.isPackaged ? path.dirname(exe) : path.dirname(BACKEND);
    backend = spawn(exe, app.isPackaged ? args : ['-u', BACKEND, ...args], {
      cwd,
      windowsHide: true,
    });
    let out = '';
    let err = '';
    const timer = setTimeout(() => reject(new Error('Il backend Python non risponde.\n' + err)), 15000);
    backend.stdout.on('data', (d) => {
      out += d.toString();
      if (out.includes('READY')) { clearTimeout(timer); resolve(); }
    });
    backend.stderr.on('data', (d) => { err += d.toString(); console.error(d.toString()); });
    backend.on('error', (e) => { clearTimeout(timer); reject(new Error(`Impossibile avviare "${PYTHON}": ${e.message}`)); });
    backend.on('exit', (code) => {
      clearTimeout(timer);
      if (out.includes('PORT_IN_USE')) {
        reject(new Error(`La porta ${PORT} è già occupata: probabilmente un'altra copia dell'editor è ancora aperta.\n` +
          'Chiudila (o termina i processi python.exe / backend.exe dal Task Manager) e riprova.'));
      } else if (!out.includes('READY')) {
        reject(new Error(`Il backend Python si è chiuso (codice ${code}).\n${err}`));
      }
    });
  });
}

ipcMain.handle('api', async (_event, route, body) => {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/api/${route}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: 'Backend non raggiungibile: ' + e.message };
  }
});

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    backgroundColor: '#14161c',
    title: 'FM07 Live Editor',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(async () => {
  try {
    await startBackend();
  } catch (e) {
    dialog.showErrorBox('FM07 Live Editor', e.message +
      (app.isPackaged ? '' : '\n\nControlla che Python sia installato e che numpy sia presente (pip install numpy).'));
    app.quit();
    return;
  }
  createWindow();
});

app.on('window-all-closed', () => app.quit());
app.on('quit', () => { if (backend) backend.kill(); });
