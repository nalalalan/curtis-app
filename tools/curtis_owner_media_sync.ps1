$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$runtime = Join-Path $repo ".runtime"
$log = Join-Path $runtime "owner-media-sync.log"
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
Set-Location $repo
$stamp = Get-Date -Format o
"[$stamp] Curtis owner media sync" | Out-File -FilePath $log -Append -Encoding utf8
python tools\curtis_owner_media_sync.py *>> $log
