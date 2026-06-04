param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath,
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$app = New-Object -ComObject Ket.Application
$app.Visible = $false
$workbook = $null
try {
  $workbook = $app.Workbooks.Open($InputPath)
  $workbook.SaveAs($OutputPath, 51)
  Write-Output "converted=$OutputPath"
}
finally {
  if ($workbook -ne $null) {
    $workbook.Close($false)
  }
  $app.Quit()
}
