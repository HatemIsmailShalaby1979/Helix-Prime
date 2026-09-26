param(
    [Parameter(Mandatory = $true)]
    [string]$Origin
)

$ErrorActionPreference = "Stop"
if ($Origin -notmatch '^https?://') { throw "Origin must be an http(s) URL" }

npx wrangler kv key put HELIX_ORIGIN $Origin --remote --binding=ORIGIN_KV --config deploy/worker/wrangler.toml