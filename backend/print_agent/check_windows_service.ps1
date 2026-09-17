$ErrorActionPreference = "Continue"

Write-Host "Windows service status:"
& sc.exe query HedePrintAgent
Write-Host ""
Write-Host "Local health endpoint:"
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:18120/health" -TimeoutSec 5
    Write-Host $response.Content
} catch {
    $errorResponse = $_.Exception.Response
    if ($errorResponse) {
        try {
            $reader = New-Object System.IO.StreamReader($errorResponse.GetResponseStream(), [Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            $reader.Dispose()
            Write-Host $body -ForegroundColor Red
        } catch {
            Write-Host $_.Exception.Message -ForegroundColor Red
        }
    } else {
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}
Write-Host ""
Write-Host "Printers visible to the signed-in user:"
try {
    Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name | Sort-Object
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}
Write-Host ""
Write-Host "Log: $env:ProgramData\HedePrintAgent\logs\service.log"
