param(
    [string]$Port = 'COM7',
    [string]$Command = "print('BREAD REPL ready')",
    [string]$CommandFile,
    [int]$TimeoutSeconds = 30
)
$ErrorActionPreference = 'Stop'
if ($CommandFile) { $Command = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $CommandFile)) }
$serial = [System.IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.DtrEnable = $true
$serial.RtsEnable = $false
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 5000
try {
    $serial.Open()
    $serial.Write([string][char]3)
    Start-Sleep -Milliseconds 250
    $serial.Write([string][char]3)
    Start-Sleep -Milliseconds 250
    $serial.DiscardInBuffer()
    $serial.Write([string][char]1)
    $handshake = [Diagnostics.Stopwatch]::StartNew()
    $prompt = ''
    while ($handshake.Elapsed.TotalSeconds -lt 5) {
        $prompt += $serial.ReadExisting()
        if ($prompt.Contains('raw REPL; CTRL-B to exit') -and $prompt.EndsWith('>')) {
            break
        }
        # A CIRCUITPY file copy can trigger autoreload during the first
        # handshake. Interrupt the restarted program and request raw REPL again.
        if ($handshake.ElapsedMilliseconds -gt 750 -and
            [int]$handshake.ElapsedMilliseconds % 750 -lt 60) {
            $serial.Write([string][char]3 + [char]1)
        }
        Start-Sleep -Milliseconds 50
    }
    if (-not $prompt.Contains('raw REPL; CTRL-B to exit')) {
        throw "Could not enter raw REPL: $prompt"
    }
    $serial.Write($Command + [char]4)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $received = ''
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $chunk = $serial.ReadExisting()
        if ($chunk.Length) {
            $received += $chunk
            [Console]::Write($chunk.Replace([string][char]4, '<EOF>'))
            if (($received.ToCharArray() | Where-Object { [int]$_ -eq 4 }).Count -ge 2) {
                break
            }
        }
        Start-Sleep -Milliseconds 50
    }
    if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
        $serial.Write([string][char]3)
        throw "Board command timed out after $TimeoutSeconds seconds"
    }
    $sections = $received.Split([char]4)
    if ($sections.Length -gt 1 -and $sections[1].Trim()) {
        throw "Board command failed: $($sections[1].Trim())"
    }
} finally {
    if ($serial.IsOpen) {
        $serial.Write([string][char]2)
        $serial.Close()
    }
    $serial.Dispose()
}
