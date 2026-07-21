param(
    [string]$DestinationRoot = "runtime_data\external"
)

$ErrorActionPreference = "Stop"
$version = "2.0.1"
$expectedSha512 = "9DB43033E31AAF21A8ABBA4130864B09DDE516AD379D7B89BB092ED7EE946E32F9F2E53EF4E50B55C324A0DBCDB894A8215EDFD5B6CF45F0F80FF2D06B94BBAA"
$url = "https://registry.npmjs.org/hanzi-writer-data/-/hanzi-writer-data-$version.tgz"
$destination = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $DestinationRoot))
$archive = Join-Path $destination "hanzi-writer-data-$version.tgz"
$extractRoot = Join-Path $destination "hanzi-writer-data-$version"
$packageDir = Join-Path $extractRoot "package"

New-Item -ItemType Directory -Force -Path $destination | Out-Null
if (-not (Test-Path -LiteralPath $archive)) {
    $temporary = "$archive.download"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temporary
    Move-Item -LiteralPath $temporary -Destination $archive
}

$actualSha512 = (Get-FileHash -Algorithm SHA512 -LiteralPath $archive).Hash
if ($actualSha512 -ne $expectedSha512) {
    throw "Hanzi Writer Data archive SHA-512 mismatch: $actualSha512"
}

if (-not (Test-Path -LiteralPath (Join-Path $packageDir "package.json"))) {
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    tar -xzf $archive -C $extractRoot
}

if (-not (Test-Path -LiteralPath (Join-Path $packageDir "ARPHICPL.TXT"))) {
    throw "ARPHICPL.TXT is missing after extraction"
}

Write-Output $packageDir
