param([string]$Port = 'COM7', [int]$ReadSeconds = 6)
# Restart code.py and close the port without interrupting the running program.
$ErrorActionPreference = 'Stop'
$serial = [System.IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.DtrEnable = $true
$serial.WriteTimeout = 5000
try {
    $serial.Open()
    $serial.Write([string][char]3 + [char]2)
    Start-Sleep -Milliseconds 150
    $serial.DiscardInBuffer()
    $serial.Write([string][char]4)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $received = ''
    while ($timer.Elapsed.TotalSeconds -lt $ReadSeconds) {
        $chunk = $serial.ReadExisting()
        $received += $chunk
        [Console]::Write($chunk)
        Start-Sleep -Milliseconds 50
    }
    if ($received.Contains('Traceback')) {
        throw 'Startup failed; see the board traceback above'
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
