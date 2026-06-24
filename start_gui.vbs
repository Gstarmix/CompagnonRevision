Option Explicit
Dim Shell, FSO, Here, ScriptPath, PythonW, Cmd
Set Shell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
Here = FSO.GetParentFolderName(WScript.ScriptFullName)
ScriptPath = FSO.BuildPath(Here, "gui.py")
PythonW = "pythonw.exe"
If Not InPath(PythonW) Then
    Dim Candidates(2), i
    Candidates(0) = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
    Candidates(1) = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe")
    Candidates(2) = "C:\Python312\pythonw.exe"
    For i = 0 To UBound(Candidates)
        If FSO.FileExists(Candidates(i)) Then
            PythonW = Candidates(i)
            Exit For
        End If
    Next
End If
If Not InPath(PythonW) And Not FSO.FileExists(PythonW) Then
    PythonW = "python.exe"
End If
Cmd = """" & PythonW & """ """ & ScriptPath & """"
Shell.CurrentDirectory = Here
Shell.Run Cmd, 0, False
Function InPath(exeName)
    On Error Resume Next
    Dim out
    out = Shell.Run("cmd /c where " & exeName & " >nul 2>&1", 0, True)
    InPath = (Err.Number = 0 And out = 0)
    On Error Goto 0
End Function