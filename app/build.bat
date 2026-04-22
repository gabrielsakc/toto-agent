@echo off
:: Build TotoAgent.exe (run from the app\ folder)
echo === Toto agent builder ===
C:\Python310\python.exe -m PyInstaller TotoAgent.spec --noconfirm
echo.
echo Build complete: dist\TotoAgent.exe
pause
