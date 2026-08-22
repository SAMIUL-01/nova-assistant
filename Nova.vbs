' ==========================================================================
'  Nova launcher  -  no black window, no typing.
'
'  Double-click this (or the desktop shortcut it creates) and Nova opens in
'  its own clean app window.
'
'  What it does:
'    1. checks Nova is set up
'    2. starts the server hidden in the background (logs to nova.log)
'    3. waits until the server answers
'    4. opens Nova in app mode (no address bar) if Chrome/Edge/Brave exists
'
'  To stop Nova later, run STOP-NOVA.bat
' ==========================================================================

Option Explicit

Dim fso, sh, scriptDir, pyExe, logFile, url, q, cmd, i, started
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

q = Chr(34)
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
url = "http://127.0.0.1:8000"
pyExe = scriptDir & "\venv\Scripts\python.exe"
logFile = scriptDir & "\nova.log"

' ---- 1. is Nova set up? --------------------------------------------------
If Not fso.FileExists(pyExe) Then
    MsgBox "Nova is not set up yet." & vbCrLf & vbCrLf & _
           "Please run SETUP.bat first (just once).", 48, "Nova"
    WScript.Quit 1
End If

If Not fso.FileExists(scriptDir & "\.env") Then
    MsgBox "Nova has no configuration yet." & vbCrLf & vbCrLf & _
           "Please run SETUP.bat first.", 48, "Nova"
    WScript.Quit 1
End If

' ---- 2. start the server if it is not already running --------------------
If Not ServerUp(url) Then
    sh.CurrentDirectory = scriptDir
    cmd = "cmd /c " & q & q & pyExe & q & _
          " -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> " & _
          q & logFile & q & " 2>&1" & q
    sh.Run cmd, 0, False        ' 0 = completely hidden

    started = False
    For i = 1 To 80              ' wait up to 40 seconds
        WScript.Sleep 500
        If ServerUp(url) Then
            started = True
            Exit For
        End If
    Next

    If Not started Then
        MsgBox "Nova could not start." & vbCrLf & vbCrLf & _
               "Run DOCTOR.bat to see what is wrong, or open nova.log " & _
               "for the technical details.", 48, "Nova"
        WScript.Quit 1
    End If
End If

' ---- 3. open it ----------------------------------------------------------
OpenApp url


' ==========================================================================
Function ServerUp(u)
    Dim http
    ServerUp = False
    On Error Resume Next
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", u & "/api/health", False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 Then ServerUp = True
    End If
    Err.Clear
    On Error GoTo 0
End Function


Sub OpenApp(u)
    ' Prefer a Chromium browser in --app mode: a clean window with no tabs
    ' or address bar, so Nova looks like a real desktop application.
    Dim browsers, p, pf, pf86, lad, shell2, fso2
    Set shell2 = CreateObject("WScript.Shell")
    Set fso2 = CreateObject("Scripting.FileSystemObject")

    pf = shell2.ExpandEnvironmentStrings("%ProgramFiles%")
    pf86 = shell2.ExpandEnvironmentStrings("%ProgramFiles(x86)%")
    lad = shell2.ExpandEnvironmentStrings("%LocalAppData%")

    browsers = Array( _
        pf & "\Google\Chrome\Application\chrome.exe", _
        pf86 & "\Google\Chrome\Application\chrome.exe", _
        lad & "\Google\Chrome\Application\chrome.exe", _
        pf & "\BraveSoftware\Brave-Browser\Application\brave.exe", _
        pf86 & "\BraveSoftware\Brave-Browser\Application\brave.exe", _
        pf & "\Microsoft\Edge\Application\msedge.exe", _
        pf86 & "\Microsoft\Edge\Application\msedge.exe")

    For Each p In browsers
        If fso2.FileExists(p) Then
            shell2.Run Chr(34) & p & Chr(34) & " --app=" & u, 1, False
            Exit Sub
        End If
    Next

    ' Nothing found: fall back to the default browser.
    shell2.Run u, 1, False
End Sub
