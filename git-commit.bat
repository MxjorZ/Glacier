@echo off
setlocal enabledelayedexpansion

echo ====================================
echo    Glacier Git Commit Helper
echo ====================================
echo.

REM Get current branch
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set current_branch=%%i
echo Current branch: %current_branch%
echo.

REM List all local branches
echo Available local branches:
git branch --format="  %%(refname:short)"
echo.

set /p branch_choice="Enter branch name (or press Enter to use current '%current_branch%'): "
if "%branch_choice%"=="" set branch_choice=%current_branch%

REM Check if branch exists locally; if not, create it from current
git show-ref --verify --quiet refs/heads/%branch_choice%
if errorlevel 1 (
    echo Branch "%branch_choice%" does not exist locally. Creating it from current branch...
    git checkout -b %branch_choice%
) else (
    git checkout %branch_choice%
)

echo.
set /p commit_msg="Commit message: "
if "%commit_msg%"=="" (
    echo Commit message cannot be empty. Aborting.
    pause
    exit /b 1
)

echo.
echo Staging all changes...
git add .
echo Committing...
git commit -m "%commit_msg%"
echo Pushing to origin/%branch_choice%...
git push origin %branch_choice%

echo.
echo Done! Press any key to close.
pause