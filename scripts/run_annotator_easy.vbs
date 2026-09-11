Option Explicit

Dim fso, shell, projectRoot, bootstrap, interpreter, command, quote
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
shell.Environment("Process")("AMAP_HIDE_CONSOLE") = "1"
quote = Chr(34)

projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
bootstrap = fso.BuildPath(projectRoot, "scripts\launch_easy.py")

If fso.FileExists(fso.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe")) Then
    interpreter = quote & fso.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe") & quote
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%WINDIR%") & "\py.exe") Then
    interpreter = quote & shell.ExpandEnvironmentStrings("%WINDIR%") & "\py.exe" & quote & " -3.12"
Else
    interpreter = "pythonw"
End If

command = interpreter & " " & quote & bootstrap & quote
shell.Run command, 0, False
