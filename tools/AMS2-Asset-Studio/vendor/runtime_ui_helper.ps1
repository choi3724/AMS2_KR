param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('desktop','desktopclick','desktopkey','desktophold','desktopwheel','window','capture','click','key','wheel','wheelcapture')]
    [string]$Action,
    [string]$Output,
    [int]$X = 0,
    [int]$Y = 0,
    [int]$Delta = 0,
    [int]$Count = 1,
    [int]$HoldMs = 1000,
    [string]$Keys = '',
    [string]$ProcessName = 'AMS2AVX',
    [string]$WindowTitle = ''
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Ams2RuntimeUi {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, int data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern void keybd_event(byte virtualKey, byte scanCode, uint flags, UIntPtr extra);
}
'@

if ($Action -eq 'desktop') {
    if ([string]::IsNullOrWhiteSpace($Output)) { throw 'desktop needs -Output' }
    $virtualScreen = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $desktopBitmap = New-Object System.Drawing.Bitmap $virtualScreen.Width, $virtualScreen.Height
    $desktopGraphics = [System.Drawing.Graphics]::FromImage($desktopBitmap)
    try {
        $desktopGraphics.CopyFromScreen($virtualScreen.Left, $virtualScreen.Top, 0, 0, $desktopBitmap.Size)
        $desktopParent = Split-Path -Parent $Output
        if ($desktopParent) { [System.IO.Directory]::CreateDirectory($desktopParent) | Out-Null }
        $desktopBitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $desktopGraphics.Dispose()
        $desktopBitmap.Dispose()
    }
    Get-Item -LiteralPath $Output | Select-Object FullName,Length
    exit 0
}

if ($Action -eq 'desktopclick') {
    [Ams2RuntimeUi]::SetCursorPos($X, $Y) | Out-Null
    [Ams2RuntimeUi]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Ams2RuntimeUi]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    exit 0
}

if ($Action -eq 'desktopwheel') {
    [Ams2RuntimeUi]::SetCursorPos($X, $Y) | Out-Null
    for ($desktopWheelIndex = 0; $desktopWheelIndex -lt [Math]::Max(1, $Count); $desktopWheelIndex++) {
        [Ams2RuntimeUi]::mouse_event(0x0800, 0, 0, $Delta, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
    }
    exit 0
}

if ($Action -eq 'desktophold') {
    $desktopHoldKeys = @{
        'W' = 0x57
        'A' = 0x41
        'S' = 0x53
        'D' = 0x44
    }
    if (-not $desktopHoldKeys.ContainsKey($Keys)) { throw "desktophold unsupported: $Keys" }
    if ($HoldMs -lt 1 -or $HoldMs -gt 30000) { throw 'desktophold HoldMs must be 1..30000' }
    [Ams2RuntimeUi]::SetCursorPos($X, $Y) | Out-Null
    [Ams2RuntimeUi]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Ams2RuntimeUi]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
    $desktopHoldVirtualKey = [byte]$desktopHoldKeys[$Keys]
    [Ams2RuntimeUi]::keybd_event($desktopHoldVirtualKey, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds $HoldMs
    [Ams2RuntimeUi]::keybd_event($desktopHoldVirtualKey, 0, 0x0002, [UIntPtr]::Zero)
    exit 0
}

if ($Action -eq 'desktopkey') {
    $desktopVirtualKeys = @{
        '{ENTER}' = 0x0D
        '{ESC}' = 0x1B
        '{UP}' = 0x26
        '{DOWN}' = 0x28
        '{LEFT}' = 0x25
        '{RIGHT}' = 0x27
        '{SPACE}' = 0x20
        '{PGDN}' = 0x22
        '{END}' = 0x23
        '{F12}' = 0x7B
    }
    if (-not $desktopVirtualKeys.ContainsKey($Keys)) { throw "desktopkey unsupported: $Keys" }
    $desktopVirtualKey = [byte]$desktopVirtualKeys[$Keys]
    if ($X -ne 0 -or $Y -ne 0) {
        [Ams2RuntimeUi]::SetCursorPos($X, $Y) | Out-Null
        [Ams2RuntimeUi]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Ams2RuntimeUi]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 250
    }
    for ($desktopKeyIndex = 0; $desktopKeyIndex -lt [Math]::Max(1, $Count); $desktopKeyIndex++) {
        [Ams2RuntimeUi]::keybd_event($desktopVirtualKey, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Ams2RuntimeUi]::keybd_event($desktopVirtualKey, 0, 0x0002, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
    }
    exit 0
}

$ams2Candidates = Get-Process -Name $ProcessName -ErrorAction Stop |
    Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
if (-not [string]::IsNullOrWhiteSpace($WindowTitle)) {
    $ams2Candidates = $ams2Candidates | Where-Object { $_.MainWindowTitle -like "*$WindowTitle*" }
}
$ams2Process = $ams2Candidates | Select-Object -First 1
if (-not $ams2Process) { throw "$ProcessName has no matching main window" }
$ams2Handle = $ams2Process.MainWindowHandle
if ($ams2Handle -eq [IntPtr]::Zero) { throw "$ProcessName has no main window" }
$ams2Rect = New-Object Ams2RuntimeUi+Rect
if (-not [Ams2RuntimeUi]::GetWindowRect($ams2Handle, [ref]$ams2Rect)) { throw 'GetWindowRect failed' }

if ($Action -eq 'window') {
    [pscustomobject]@{
        Process = $ams2Process.ProcessName
        Pid = $ams2Process.Id
        Handle = $ams2Handle.ToInt64()
        Left = $ams2Rect.Left
        Top = $ams2Rect.Top
        Right = $ams2Rect.Right
        Bottom = $ams2Rect.Bottom
        Width = $ams2Rect.Right - $ams2Rect.Left
        Height = $ams2Rect.Bottom - $ams2Rect.Top
        IsForeground = ([Ams2RuntimeUi]::GetForegroundWindow() -eq $ams2Handle)
    } | ConvertTo-Json
    exit 0
}

if ($Action -eq 'capture') {
    if ([string]::IsNullOrWhiteSpace($Output)) { throw 'capture needs -Output' }
    $ams2Width = $ams2Rect.Right - $ams2Rect.Left
    $ams2Height = $ams2Rect.Bottom - $ams2Rect.Top
    $ams2Bitmap = New-Object System.Drawing.Bitmap $ams2Width, $ams2Height
    $ams2Graphics = [System.Drawing.Graphics]::FromImage($ams2Bitmap)
    try {
        $ams2Graphics.CopyFromScreen($ams2Rect.Left, $ams2Rect.Top, 0, 0, $ams2Bitmap.Size)
        $ams2Parent = Split-Path -Parent $Output
        if ($ams2Parent) { [System.IO.Directory]::CreateDirectory($ams2Parent) | Out-Null }
        $ams2Bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $ams2Graphics.Dispose()
        $ams2Bitmap.Dispose()
    }
    Get-Item -LiteralPath $Output | Select-Object FullName,Length
    exit 0
}

$shell = New-Object -ComObject WScript.Shell
$activated = $shell.AppActivate($ams2Process.Id)
$null = [Ams2RuntimeUi]::ShowWindow($ams2Handle, 9)
# A brief Alt key transition grants this input thread permission to move the
# foreground window without displaying any shell/Run UI.
[Ams2RuntimeUi]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
$foregroundSet = [Ams2RuntimeUi]::SetForegroundWindow($ams2Handle)
[Ams2RuntimeUi]::BringWindowToTop($ams2Handle) | Out-Null
[Ams2RuntimeUi]::keybd_event(0x12, 0, 0x0002, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
if ($Action -eq 'click') {
    [Ams2RuntimeUi]::SetCursorPos($ams2Rect.Left + $X, $ams2Rect.Top + $Y) | Out-Null
    [Ams2RuntimeUi]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    # AMS2 polls mouse state per frame.  A zero-duration synthetic click can
    # begin and end between two frames, leaving only the hover state visible.
    Start-Sleep -Milliseconds 80
    [Ams2RuntimeUi]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
} elseif ($Action -eq 'wheel' -or $Action -eq 'wheelcapture') {
    [Ams2RuntimeUi]::SetCursorPos($ams2Rect.Left + $X, $ams2Rect.Top + $Y) | Out-Null
    for ($ams2WheelIndex = 0; $ams2WheelIndex -lt [Math]::Max(1, $Count); $ams2WheelIndex++) {
        [Ams2RuntimeUi]::mouse_event(0x0800, 0, 0, $Delta, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 8
    }
    if ($Action -eq 'wheelcapture') {
        if ([string]::IsNullOrWhiteSpace($Output)) { throw 'wheelcapture needs -Output' }
        $ams2Width = $ams2Rect.Right - $ams2Rect.Left
        $ams2Height = $ams2Rect.Bottom - $ams2Rect.Top
        $ams2Bitmap = New-Object System.Drawing.Bitmap $ams2Width, $ams2Height
        $ams2Graphics = [System.Drawing.Graphics]::FromImage($ams2Bitmap)
        try {
            $ams2Graphics.CopyFromScreen($ams2Rect.Left, $ams2Rect.Top, 0, 0, $ams2Bitmap.Size)
            $ams2Parent = Split-Path -Parent $Output
            if ($ams2Parent) { [System.IO.Directory]::CreateDirectory($ams2Parent) | Out-Null }
            $ams2Bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $ams2Graphics.Dispose()
            $ams2Bitmap.Dispose()
        }
    }
} elseif ($Action -eq 'key') {
    $virtualKeys = @{
        '{ENTER}' = 0x0D
        '{ESC}' = 0x1B
        '{UP}' = 0x26
        '{DOWN}' = 0x28
        '{LEFT}' = 0x25
        '{RIGHT}' = 0x27
        '{SPACE}' = 0x20
        '{F12}' = 0x7B
    }
    if ($virtualKeys.ContainsKey($Keys)) {
        $virtualKey = [byte]$virtualKeys[$Keys]
        [Ams2RuntimeUi]::keybd_event($virtualKey, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Ams2RuntimeUi]::keybd_event($virtualKey, 0, 0x0002, [UIntPtr]::Zero)
    } else {
        [System.Windows.Forms.SendKeys]::SendWait($Keys)
    }
}
