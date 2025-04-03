@echo off
echo Starting PDF Signature Tool packaging...

rem Check if Python is installed
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python first.
    pause
    exit /b 1
)

rem Run the build script
echo Running build script...
python build_exe.py

if %errorlevel% neq 0 (
    echo Build process failed. Please check the logs.
) else (
    echo Build completed successfully!
    echo The executable file is in the dist directory.
)

echo.
echo Note: If PDF preview doesn't work, install Poppler:
echo https://github.com/oschwartz10612/poppler-windows/releases
echo And add its bin directory to your PATH environment variable.

pause
