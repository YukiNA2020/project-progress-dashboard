' 在隐藏窗口中启动项目进度看板。
' Windows 的软件限制策略可能禁止 pythonw.exe，因此改为用 wscript 启动
' python.exe，并把控制台窗口隐藏（窗口样式 0）。
Option Explicit

Dim fso, shell, base, python, runpy, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
python = base & "\.venv\Scripts\python.exe"
runpy = base & "\run.py"

If Not fso.FileExists(python) Then WScript.Quit 1
If Not fso.FileExists(runpy) Then WScript.Quit 1

command = """" & python & """ """ & runpy & """ serve --open-browser"
shell.Run command, 0, False
