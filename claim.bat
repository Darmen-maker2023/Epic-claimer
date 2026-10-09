@echo off
cd /d %~dp0
python claimer.py claim >> claim.log 2>&1
