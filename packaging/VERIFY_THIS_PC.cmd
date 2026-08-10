@echo off
chcp 65001 >nul
title GFM Stability Platform - Cross-machine Acceptance
echo 正在核对发布包并执行本机功能验收，请勿关闭窗口。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_this_pc.ps1"
set "GFM_EXIT_CODE=%ERRORLEVEL%"
echo.
if "%GFM_EXIT_CODE%"=="0" (
  echo 验收脚本已完成。请把 acceptance-results 文件夹发给项目负责人。
) else (
  echo 验收未通过。请把 acceptance-results 文件夹和本窗口截图发给项目负责人。
)
echo.
pause
exit /b %GFM_EXIT_CODE%

