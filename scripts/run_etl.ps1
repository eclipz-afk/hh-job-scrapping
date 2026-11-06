param(
    [int]$TargetRows = 5000
)

if ($TargetRows -lt 1 -or $TargetRows -gt 10000) {
    throw 'TargetRows must be between 1 and 10000.'
}
$token = Read-Host 'ETL access token' -AsSecureString
$credential = New-Object System.Net.NetworkCredential('', $token)
$headers = @{ Authorization = 'Bearer ' + $credential.Password }
try {
    $body = @{ target_rows = $TargetRows } | ConvertTo-Json
    Invoke-RestMethod -Method POST -Uri 'http://localhost:5000/api/v1/etl/run' -ContentType 'application/json' -Headers $headers -Body $body
} finally {
    $headers.Clear()
    $credential = $null
    $token.Dispose()
}
