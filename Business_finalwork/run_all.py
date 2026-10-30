from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_analysis() -> None:
    subprocess.run([sys.executable, "main.py"], cwd=ROOT, check=True)


def capture_dashboard() -> None:
    html = ROOT / "outputs" / "dashboard.html"
    output = ROOT / "outputs" / "figures" / "Superstore交互式经营看板.png"
    if not html.exists():
        print("[skip] dashboard.html 未生成，跳过截图。")
        return
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    browser = next((path for path in candidates if path and Path(path).exists()), None)
    if not browser:
        print("[skip] 未找到Chrome或Edge，跳过看板截图；dashboard.html仍可正常打开。")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--window-size=1600,1800",
            "--virtual-time-budget=5000",
            f"--screenshot={output}",
            html.resolve().as_uri(),
        ],
        cwd=ROOT,
        check=False,
    )
    print(f"[done] 看板截图：{output}")


if __name__ == "__main__":
    run_analysis()
    capture_dashboard()
    print("[done] 全部分析、图表和看板已生成。")
