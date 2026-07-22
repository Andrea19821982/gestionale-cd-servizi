@echo off
rem Doppio clic su questo file per aggiornare "Calendario Turni" a partire
rem da un file .bundle copiato nella stessa cartella (vedi il foglio Word
rem con le istruzioni). Non serve altro: lo script fa tutto da solo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aggiorna_programma.ps1"
