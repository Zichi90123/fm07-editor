@echo off
cd /d "%~dp0"
echo Controllo numpy...
python -c "import numpy" 2>nul || python -m pip install -r backend\requirements.txt
cd app
if not exist node_modules (
  echo Prima installazione di Electron, attendi...
  call npm install
)
call npm start
