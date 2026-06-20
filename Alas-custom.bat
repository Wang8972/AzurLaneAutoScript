@rem  Custom Alas launcher: sync official upstream into your fork branch, then start Alas.
@rem  Double-click THIS file instead of Alas.exe.
@rem  Requires (one-time setup, see plan / README):
@rem    - config/deploy.yaml -> Repository = your fork (with PAT), Branch = the branch set in _branch below
@rem    - `origin` remote pointing to your fork (set automatically by deploy.installer after first run)
@echo off

set "_root=%~dp0"
set "_root=%_root:~0,-1%"
cd "%_root%"

color F0

set "_pyBin=%_root%\toolkit"
set "_GitBin=%_root%\toolkit\Git\mingw64\bin"
set "_adbBin=%_root%\toolkit\Lib\site-packages\adbutils\binaries"
set "PATH=%_root%\toolkit\alias;%_root%\toolkit\command;%_pyBin%;%_pyBin%\Scripts;%_GitBin%;%_adbBin%;%PATH%"

@rem ===== EDIT THESE IF NEEDED =====
set "_branch=custom"
set "_upstream=git@github.com:LmeSzinc/AzurLaneAutoScript.git"
@rem ================================

title Alas Custom Updater

@rem ----- sync official upstream into your fork branch -----
git remote get-url upstream >nul 2>&1 || git remote add upstream "%_upstream%"

echo [custom] Fetching official upstream...
git fetch upstream master
if errorlevel 1 (
    echo [custom] WARNING: fetch upstream failed ^(network/proxy^). Skipping merge, launching current version.
    goto :run
)

git checkout %_branch%
if errorlevel 1 (
    echo [custom] WARNING: cannot checkout branch "%_branch%" ^(uncommitted changes or branch missing^).
    echo [custom]          Skipping merge, launching current version.
    goto :run
)

echo [custom] Merging upstream/master into %_branch%...
git merge --no-edit upstream/master
if errorlevel 1 (
    echo [custom] ============================================================
    echo [custom]  MERGE CONFLICT. Official update SKIPPED this run.
    echo [custom]  Your local changes are SAFE ^(already on your fork^).
    echo [custom]  Resolve manually later, then push:
    echo [custom]    git merge upstream/master   ^(fix conflicts^)
    echo [custom]    git push origin %_branch%
    echo [custom] ============================================================
    git merge --abort
) else (
    echo [custom] Merge OK. Pushing to your fork...
    git push origin %_branch%
    if errorlevel 1 (
        echo [custom] WARNING: push failed ^(check fork URL / token in config/deploy.yaml^).
        echo [custom]          Update not applied this run; local changes remain safe.
    )
)

:run
title Alas Updater
python -m deploy.installer
if %errorlevel% neq 0 (
    pause >nul
) else (
    start "Alas" "%_root%\toolkit\webapp\alas.exe"
)
