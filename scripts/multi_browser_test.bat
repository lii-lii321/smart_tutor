@echo off
rem ==================================================
rem Multi-role browser testing for smart_tutor.
rem Each Edge instance gets an isolated user-data-dir,
rem so cookies/sessions never leak between windows.
rem
rem Demo accounts (DEV_MODE seed, password: dev123456)
rem   Tenant : /owner/login    invite codes: tx886 / jj2026
rem   Teacher: /teacher/login  phones: 13900000001 - 13900000004
rem ==================================================

set EDGE="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set BASE=http://localhost:5173
set PROFILE_ROOT=%LOCALAPPDATA%\smart_tutor_test_profiles

rem Window 1: tenant admin, desktop size
start "tenant-admin" %EDGE% --user-data-dir="%PROFILE_ROOT%\tenant" --window-size=1280,900 "%BASE%/owner/login"

rem Window 2: teacher A, phone-shaped (H5 board is mobile-first)
start "teacher-a" %EDGE% --user-data-dir="%PROFILE_ROOT%\teacher-a" --window-size=414,896 "%BASE%/teacher/login"

rem Window 3: teacher B, second isolated identity
start "teacher-b" %EDGE% --user-data-dir="%PROFILE_ROOT%\teacher-b" --window-size=414,896 "%BASE%/teacher/login"

echo Launched 3 isolated windows:
echo   tenant    %BASE%/owner/login
echo   teacher A %BASE%/teacher/login  (13900000001)
echo   teacher B %BASE%/teacher/login  (13900000002)
echo Password for all demo accounts: dev123456
