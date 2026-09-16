@echo off
chcp 65001 >nul
title 关掉 Windows 智能应用控制 (Smart App Control)
echo.
echo 本脚本将尝试关闭「智能应用控制」(Smart App Control)。
echo 需要管理员权限。关掉后通常无法再打开，除非重装系统。
echo.
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [!] 请右键本文件 - 以管理员身份运行
  pause
  exit /b 1
)

echo [1/3] 写入策略：VerifiedAndReputablePolicy=0
reg add "HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy" /v VerifiedAndReputablePolicy /t REG_DWORD /d 0 /f

echo [2/3] 关闭 SmartScreen 相关（可选）
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer" /v SmartScreenEnabled /t REG_SZ /d Off /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\System" /v EnableSmartScreen /t REG_DWORD /d 0 /f >nul 2>&1

echo [3/3] 尝试关闭 Defender 实时防护（若组策略锁定可能失败）
powershell -NoProfile -Command "Try { Set-MpPreference -DisableRealtimeMonitoring $true; Set-MpPreference -DisableBehaviorMonitoring $true; 'Realtime OFF' } Catch { $_.Exception.Message }"

echo.
echo 完成。请重启电脑后检查：
echo   设置 - 隐私和安全性 - Windows 安全中心 - 应用和浏览器控制 - 智能应用控制
echo 状态应为「关闭」。
echo.
pause
