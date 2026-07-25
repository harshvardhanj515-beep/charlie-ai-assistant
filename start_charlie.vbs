Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Harshvardhan Sheikh\Downloads\charlie"
WshShell.Run "cmd /c venv\Scripts\activate & python run.py", 0, False
