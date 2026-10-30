param(
  [int]$Port = 8092,
  [int]$Pool = 64000,
  [int]$Hostkv = 8192,
  [string]$Dtype = "rk2v4-e8",
  [int]$MaxCtx = 262144,
  [int]$Window = 16384,
  [string]$Retrieve = "",
  [switch]$Mtp,
  [int]$Chunk = 1024,
  [string]$Tag = "exp",
  [string]$Extra = ""
)
$env:NINFER_KV_WINDOW = "$Window"
$env:NINFER_HOST_PAGEABLE = "1"
$env:NINFER_KV_REUSE_HOSTBACKED = "1"
$env:NINFER_TERNARY_PTQ1_FAST = "1"
if ($Retrieve -ne "") { $env:NINFER_KV_RETRIEVE = $Retrieve } else { Remove-Item Env:NINFER_KV_RETRIEVE -ErrorAction SilentlyContinue }
$root = "C:/Project/local_model"
$eng = "$root/engine/ninfer-serve-89.exe"
$model = "$root/models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
$argv = @($model, "--host","127.0.0.1","--port",$Port, "--model-id","exp-long-$Port",
  "--max-context",$MaxCtx,"--kv-capacity",$Pool,"--kv-dtype",$Dtype,"--host-kv-mib",$Hostkv,
  "--max-concurrency","1","--max-shared-prefixes","0","--derive-session-keys",
  "--prefill-chunk",$Chunk,"--no-cuda-graph","--device-state-slots","0","--gdn-state-fp16",
  "--presence-penalty","0","--temperature","0.7","--top-p","0.9","--top-k","20",
  "--default-reasoning-effort","none","--default-max-tokens","4096",
  "--log-stats-interval-ms","5000","--log-colours","off")
if ($Mtp) { $argv += @("--spec","mtp","--draft-tokens","4","--mtp-attention-window","8") }
if ($Extra -ne "") { $argv += $Extra.Split(" ") }
Write-Host ("[exp] " + ($argv -join " "))
Start-Process -FilePath $eng -ArgumentList $argv -WindowStyle Hidden -RedirectStandardOutput "$root/logs/exp-$Tag.log" -RedirectStandardError "$root/logs/exp-$Tag.err"
Write-Host "[exp] started tag=$Tag port=$Port pool=$Pool dtype=$Dtype hostkv=$Hostkv window=$Window retrieve=$Retrieve mtp=$Mtp"