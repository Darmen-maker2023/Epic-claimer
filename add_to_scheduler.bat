@echo off
rem Schedule EpicClaimer.exe (preferred) or claim.bat:
rem   daily at 18:30 (after Epic's Thursday 18:00 MSK drop) + on logon
set EXE=%~dp0EpicClaimer.exe
if exist "%EXE%" (
  schtasks /Create /F /TN "EpicFreeGamesClaimer" /TR "\"%EXE%\" --claim" /SC DAILY /ST 18:30
  schtasks /Create /F /TN "EpicFreeGamesClaimerLogon" /TR "\"%EXE%\" --claim" /SC ONLOGON
) else (
  schtasks /Create /F /TN "EpicFreeGamesClaimer" /TR "\"%~dp0claim.bat\"" /SC DAILY /ST 18:30
  schtasks /Create /F /TN "EpicFreeGamesClaimerLogon" /TR "\"%~dp0claim.bat\"" /SC ONLOGON
)
echo Done.
pause
