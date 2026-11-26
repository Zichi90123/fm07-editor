const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fm', {
  api: (route, body) => ipcRenderer.invoke('api', route, body),
});
