# 使用问题记录（Windows 端）

本文件用于收集在 Windows 上日常使用「项目进度看板」时发现的问题，之后在 Mac 上统一修改。
每条问题尽量保留：现象、复现步骤、预期、实际、环境、证据（截图/日志）、状态。

- 记录起点：2026-11-03
- 使用环境：Windows + PowerShell 5，项目位于 `D:\Project_Dashboard`
- 数据目录：`C:\Users\26026373\AppData\Local\ProjectProgressDashboard`
- 服务地址：`http://127.0.0.1:8000`
- Python：3.13.15（`backend\.venv`），Node：24.20.0

---

## 待处理问题

| ID | 问题 | 优先级 | 状态 |
| --- | --- | --- | --- |
| W-001 | 桌面 `Agent` 文件夹里看不到「项目进度看板」快捷方式 | 高 | 已解决（改放桌面根目录） |
| W-003 | `verify_phase3.py` 在 Windows 上密钥权限断言失败 | 低 | 未修改 |
| W-004 | 登录自启时会自动打开浏览器 | 中 | 待决定 |
| W-005 | 测试遗留空目录 `.runtime-test/` | 低 | 待清理 |

### W-001 桌面快捷方式未显示

**现象**

通过 `WScript.Shell` 在 `[Environment]::GetFolderPath('Desktop') + \Agent\项目进度看板.lnk` 创建快捷方式，创建与回读均成功，但资源管理器的 `Desktop\Agent` 中只看到原有的 8 个快捷方式，没有新增项。

**已有信息**

- 快捷方式目标：`C:\Windows\System32\wscript.exe`
- 参数：`"D:\Project_Dashboard\backend\launch_hidden.vbs"`
- 工作目录：`D:\Project_Dashboard\backend`
- 图标：`D:\Project_Dashboard\backend\.venv\Scripts\python.exe`

**可能原因（按可能性排序）**

1. 桌面被 OneDrive 或企业策略重定向，`GetFolderPath('Desktop')` 返回的目录与资源管理器里看到的目录不一致。
2. 资源管理器未刷新（F5 后仍不存在则可排除）。
3. 快捷方式被创建到了另一个用户/另一个 Desktop 路径。
4. 文件名或扩展名被安全软件处理。

**下一步（Windows 上确认）**

- 在资源管理器打开 `Agent` 文件夹，看地址栏的完整路径。
- 对比 `[Environment]::GetFolderPath('Desktop')` 的返回值。
- 分别列出 `C:\Users\26026373\Desktop\Agent` 和 OneDrive 下 `Desktop\Agent` 的内容。
- 若只是重定向，直接在用户实际看到的 `Agent` 目录再建一次即可。

**2026-11-03 处理结果**

- 实际桌面已确认：`C:\Users\26026373\Desktop`（该目录下 `Agent\OpenCode.lnk` 存在，与截图的 8 个快捷方式一致）。
- 快捷方式已改放到桌面根目录：`C:\Users\26026373\Desktop\项目进度看板.lnk`，创建后复查仍存在。
- 之前放在 `Agent` 内的副本在创建/回读成功后消失，原因未查明（疑似安全软件或同步清理），目前不再使用该位置。

**Mac 上要改什么**

如果后续仍要提供“放进 Agent 文件夹”的版本，需要先确认目标目录的实际路径，并在创建后复查文件是否被安全软件移除；不建议假设 `~/Desktop/Agent` 一定存在。

### W-003 `verify_phase3.py` 在 Windows 上失败 1 项

**现象**

`backend\.venv\Scripts\python.exe backend\verify_phase3.py` 结果为 74/75，唯一失败项是“密钥文件在数据目录且权限为 0600”，Windows 上实际为 `0o666`。

**原因**

Windows 的 `os.chmod` 不映射 POSIX 权限位；密钥文件仍位于用户私有的 `LOCALAPPDATA`，默认继承用户目录 ACL。

**Mac 上要改什么**

校验脚本按平台区分：Windows 不检查 POSIX mode，改为检查文件位于用户数据目录且不在仓库内；或在文档中明确 Windows 的等价保证是目录 ACL。

### W-004 登录自启自动打开浏览器

**现象**

登录自启命令走 `backend/launch_hidden.vbs`，其中固定带 `--open-browser`，因此每次登录都会弹出一次浏览器。

**选项**

- 保留：登录即可看到看板，但每天多一个浏览器窗口。
- 去掉 `--open-browser`：只后台起服务，用户双击桌面快捷方式时再打开浏览器。

**Mac 上要改什么**

如果决定去掉，需要同时调整 Windows 启动器和桌面快捷方式的行为（或给启动器加一个“是否打开浏览器”的参数）。

### W-005 `.runtime-test/` 空目录

**现象**

Windows 验证时在仓库根目录留下空的 `.runtime-test/`（内部文件已删除，仅剩空目录）。

**处理**

不影响运行；可直接删除。Git 不跟踪空目录，因此不会进入提交。

---

## 已在 Windows 修复、需要同步到 Mac 的改动

> 这些改动目前只存在于这台 Windows 的工作区，尚未提交。到 Mac 后需要 review 并合并。

- [x] `backend/launch_hidden.vbs`（新增）：用 `wscript` 隐藏窗口启动 `python.exe`。
- [x] `backend/app/system/__init__.py`：Windows 启动命令改为 `wscript.exe + launch_hidden.vbs`，判断依据改为 `platform_id()`，保证 macOS 模拟测试仍能通过。
- [x] `backend/verify_phase4.py`：Windows 启动项断言改为检查隐藏启动器；补充非 POSIX 系统上的 `_uid` 模拟；路径断言兼容 `\`。
- [x] `ARCHITECTURE.md`：同步 Windows 登录启动的说明。

**背景**

这台机器有软件限制策略，直接运行 `pythonw.exe` 报错：

```text
程序“pythonw.exe”无法运行: Access to %1 has been restricted by your Administrator by policy rule %2
```

因此不能依赖 `pythonw.exe` 静默启动。macOS 端不受影响。

**验证结果**

- `verify_phase2.py`：30/30
- `verify_phase4.py`：73/73（Windows）
- `verify_phase3.py`：74/75（仅 W-003）
- 真实浏览器：中文界面、月历、项目详情均正常
- 桌面快捷方式启动链路：隐藏启动服务 + 自动打开浏览器，已验证

---

## 新问题模板

```markdown
### W-XXX 标题

**发现日期**：YYYY-MM-DD
**环境**：Windows / macOS，版本；服务版本或 commit
**优先级**：高 / 中 / 低

**现象**
（发生了什么，尽量附截图路径）

**复现步骤**
1.
2.
3.

**预期**

**实际**

**日志/证据**
- 日志：`...\logs\dashboard.log` 相关片段
- 截图：`...`

**初步判断**

**Mac 上要改什么**
```
