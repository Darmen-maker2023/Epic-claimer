# Android companion

This native Android app displays currently active Epic Games free offers and opens each product page in the browser. Sign in to Epic in the browser and finish checkout there.

The existing desktop claimer uses Playwright and a desktop Chromium profile. Android WebView does not share that session or browser automation, so the mobile app intentionally leaves sign-in and checkout in the user's browser.

Build a locally signed APK from the repository root with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android.ps1
```

The output is `dist/EpicClaimer-Android.apk`. The script uses the Android SDK bundled with Unity and signs with a local debug key for direct installation.
