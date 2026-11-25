@echo off
chcp 65001 >nul
cd /d "%~dp0"
"C:\Users\Huawei\AppData\Local\Python\bin\python.exe" autoposter.py post-next %*
