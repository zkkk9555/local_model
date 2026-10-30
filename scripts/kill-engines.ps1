Get-CimInstance Win32_Process -Filter "Name like '%ninfer%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ("killed " + $_.ProcessId) }
Get-CimInstance Win32_Process -Filter "Name like '%python%'" | Where-Object { $_.CommandLine -like "*chat_gateway*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ("killed gateway " + $_.ProcessId) }
Start-Sleep -Seconds 4
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader