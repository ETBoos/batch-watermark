# 关掉 Windows「智能应用控制」(Smart App Control)

适用：Win11 笔记本上安装本工具时被拦截/误删。

## 一键（推荐）

1. 右键仓库里的 `关掉智能应用控制.bat`
2. 选择 **以管理员身份运行**
3. **重启电脑**
4. 打开：`设置 → 隐私和安全性 → Windows 安全中心 → 应用和浏览器控制 → 智能应用控制`  
   确认状态为 **关闭**

## 手动设置路径

1. `Win + I` 打开设置  
2. **隐私和安全性** → **Windows 安全中心** → 打开 Windows 安全中心  
3. **应用和浏览器控制** → **智能应用控制** 设置  
4. 选 **关闭**

> 注意：微软设计为「关掉后多数机器不能再打开」，除非重置/重装系统。确认你需要长期关闭再操作。

## 若仍删本工具

给项目目录加 Defender 排除（管理员 PowerShell）：

```powershell
Add-MpPreference -ExclusionPath "$env:USERPROFILE\我的项目\batch-watermark"
Set-MpPreference -DisableRealtimeMonitoring $true
```

或：Windows 安全中心 → 病毒和威胁防护 → 管理设置 → 排除项 → 添加文件夹。
