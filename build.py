import subprocess
import sys
import os

APP_NAME = "EaaS_AutoCommerce_OS"
ENTRY = "main.py"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    f"--name={APP_NAME}",
    "--collect-all", "customtkinter",
    "--collect-all", "matplotlib",
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=google.generativeai",
    ENTRY,
]

print("Building EaaS Auto-Commerce OS .exe ...")
print(" ".join(cmd))
result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
if result.returncode == 0:
    print(f"\nBuild basarili! dist/{APP_NAME}.exe dosyasi olusturuldu.")
else:
    print("\nBuild basarisiz. Yukaridaki hatalara bakin.")
    sys.exit(1)
