$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$editorRoot = 'C:\Program Files\Unity\Hub\Editor'
$androidRoot = Get-ChildItem -LiteralPath $editorRoot -Directory -ErrorAction Stop |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName 'Editor\Data\PlaybackEngines\AndroidPlayer' } |
    Where-Object { Test-Path (Join-Path $_ 'SDK\platforms\android-32\android.jar') } |
    Select-Object -First 1
if (-not $androidRoot) { throw 'Unity Android SDK (API 32) was not found.' }

$sdk = Join-Path $androidRoot 'SDK'
$platform = Join-Path $sdk 'platforms\android-32\android.jar'
$tools = Join-Path $sdk 'build-tools\32.0.0'
$javac = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.1.12-hotspot\bin\javac.exe'
$java = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.1.12-hotspot\bin\java.exe'
$keytool = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.1.12-hotspot\bin\keytool.exe'
$jarTool = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.1.12-hotspot\bin\jar.exe'
foreach ($path in @($platform, "$tools\aapt.exe", "$tools\d8.bat", "$tools\zipalign.exe", "$tools\apksigner.bat", $javac, $java, $keytool, $jarTool)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Android build tool missing: $path" }
}

$work = Join-Path $project 'build\android-apk'
$classes = Join-Path $work 'classes'
$resApk = Join-Path $work 'resources-unsigned.apk'
$unsigned = Join-Path $work 'unsigned.apk'
$aligned = Join-Path $work 'aligned.apk'
$apk = Join-Path $project 'dist\EpicClaimer-Android.apk'
$keystore = Join-Path $work 'debug.keystore'
New-Item -ItemType Directory -Force -Path $classes,(Split-Path -Parent $apk) | Out-Null
Remove-Item -LiteralPath $classes -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $classes | Out-Null

& "$tools\aapt.exe" package -f -M (Join-Path $project 'android\AndroidManifest.xml') -S (Join-Path $project 'android\res') -I $platform -F $resApk
if ($LASTEXITCODE -ne 0) { throw 'aapt resource packaging failed.' }
& $javac -encoding UTF-8 -source 7 -target 7 -bootclasspath $platform -d $classes (Join-Path $project 'android\src\com\epicclaimer\mobile\MainActivity.java')
if ($LASTEXITCODE -ne 0) { throw 'javac compilation failed.' }
& $jarTool cf (Join-Path $work 'classes.jar') -C $classes .
if ($LASTEXITCODE -ne 0) { throw 'Java class packaging failed.' }
& "$tools\d8.bat" --lib $platform --min-api 23 --output $work (Join-Path $work 'classes.jar')
if ($LASTEXITCODE -ne 0) { throw 'D8 dex compilation failed.' }
Push-Location $work
& "$tools\aapt.exe" add $resApk 'classes.dex'
$addDexStatus = $LASTEXITCODE
Pop-Location
if ($addDexStatus -ne 0) { throw 'Adding DEX to APK failed.' }
Move-Item -LiteralPath $resApk -Destination $unsigned -Force
& "$tools\zipalign.exe" -f 4 $unsigned $aligned
if ($LASTEXITCODE -ne 0) { throw 'APK alignment failed.' }
if (-not (Test-Path -LiteralPath $keystore)) {
    & $keytool -genkeypair -keystore $keystore -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Epic Claimer Debug,O=Local Build,C=US' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Debug signing key generation failed.' }
}
& "$tools\apksigner.bat" sign --ks $keystore --ks-pass pass:android --key-pass pass:android --out $apk $aligned
if ($LASTEXITCODE -ne 0) { throw 'APK signing failed.' }
& "$tools\apksigner.bat" verify --verbose $apk
if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
Write-Output "Android APK created: $apk"
