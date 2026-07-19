Set WshShell = CreateObject("WScript.Shell")
' 0 means vbHide (hidden window), False means don't wait for completion
WshShell.Run "cmd /c """ & CreateObject("Scripting.FileSystemObject").GetAbsolutePathName(".") & "\venv\Scripts\python.exe"" main.py", 0, False
