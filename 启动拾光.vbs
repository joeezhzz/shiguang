' 拾光启动器（通用版）
' 用 py launcher 的 pyw（GUI 子系统，无控制台窗口）静默启动，自动定位本脚本所在目录
' 前提：已安装 Python 3.10+（勾选 py launcher，默认勾选），并 pip install -r requirements.txt
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
ws.Run "pyw src\main.py", 0, False
