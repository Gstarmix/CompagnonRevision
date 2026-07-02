' start_gui.vbs : lanceur silencieux de la GUI Compagnon (Tkinter).
'
' Double-clic pour ouvrir la fenêtre Tk sans console derrière. Préfère
' pythonw.exe (pas de fenêtre cmd qui s'ouvre) ; fallback sur python.exe
' si introuvable.
'
' Pattern calqué sur Arsenal_Arguments\start_summarize_gui.vbs.

Option Explicit

Dim Shell, FSO, Here, ScriptPath, PythonW, Cmd
Set Shell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

Here = FSO.GetParentFolderName(WScript.ScriptFullName)
ScriptPath = FSO.BuildPath(Here, "gui.py")

' 1. PATH (cherche pythonw.exe directement)
PythonW = "pythonw.exe"

' 2. Fallback : chemins courants Python 3.12 user-local
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

' 3. Dernière chance : python.exe (ouvrira une console parasite mais marchera)
If Not InPath(PythonW) And Not FSO.FileExists(PythonW) Then
    PythonW = "python.exe"
End If

Cmd = """" & PythonW & """ """ & ScriptPath & """"
Shell.CurrentDirectory = Here
Shell.Run Cmd, 0, False  ' 0 = pas de fenêtre, False = ne pas attendre

Function InPath(exeName)
    On Error Resume Next
    Dim out
    out = Shell.Run("cmd /c where " & exeName & " >nul 2>&1", 0, True)
    InPath = (Err.Number = 0 And out = 0)
    On Error Goto 0
End Function
