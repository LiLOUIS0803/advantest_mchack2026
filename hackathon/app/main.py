"""
App 進入點。對應 md 開發流程：

  本機：`python3 main.py`（用 oneapi_mock，不會真的連線，只是確認 import/初始化沒壞掉）
  Gemini Edge Server：由 runTp.sh / Docker container 啟動，這時 `import oneapi`
    要換成官方真正的 SDK（第一次上機時請對照 ONEAPI 手冊確認 import 路徑）。

要在本機完整跑過一次 consumeData()/consumeTPRequest() 的邏輯（不需要真的 Nexus
連線），請用 `python3 replay.py`，它會把 25 片 wafer 的 CSV 資料當成 STDF replay
的即時事件序列餵進 SampleMonitor，等同 md 第 7 節說的「STDF replay 驗證」。
"""

from __future__ import annotations

import logging

from sample import SampleMonitor

try:
    from oneapi import AppInfo, Interface  # type: ignore
except ImportError:
    from oneapi_mock import AppInfo, Interface

log = logging.getLogger("acs_rtdi_app")


def main():
    info = AppInfo(name="acs-rtdi-app", version="0.1")
    Interface.connect(info)
    Interface.registerMonitor(SampleMonitor())
    log.info("App started, waiting for Nexus events... (Ctrl+C to stop)")
    try:
        while True:
            pass  # 真正 SDK 會在背景 thread 持續呼叫 monitor 的 callback，這裡只需要保持存活
    except KeyboardInterrupt:
        Interface.disconnect()


if __name__ == "__main__":
    main()
