@echo off
rem Crea l'eseguibile portatile in app\dist\ (serve Python 3.9+ e Node.js 18+ solo per chi compila)
cd /d "%~dp0"
setlocal

echo [1/3] Backend Python -^> backend.exe
if not exist .venv-build python -m venv .venv-build || goto :err
call .venv-build\Scripts\activate.bat
python -m pip install --quiet --upgrade pip || goto :err
python -m pip install --quiet -r backend\requirements.txt pyinstaller || goto :err
pushd backend
pyinstaller --noconfirm --clean --onedir --console --name backend server.py || (popd & goto :err)
popd

echo [2/3] Dipendenze Electron
pushd app
call npm ci || (popd & goto :err)

echo [3/3] Eseguibile portatile
call npm run dist || (popd & goto :err)
popd

echo.
echo Fatto: trovi l'exe in app\dist\
goto :eof

:err
echo.
echo ERRORE durante la build.
exit /b 1
