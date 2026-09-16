@echo off
copy /Y "%~dp0plugin.js" "%LOCALAPPDATA%\hermes\desktop-plugins\interactive-artifacts\plugin.js"
echo deployed to %%LOCALAPPDATA%%\hermes\desktop-plugins\interactive-artifacts\plugin.js
