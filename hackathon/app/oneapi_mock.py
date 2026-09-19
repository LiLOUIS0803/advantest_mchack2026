"""
OneAPI SDK 本機模擬層。

⚠️ 重要：這個檔案只是為了讓 sample.py 可以在沒有 Gemini VM / 沒有真的
ACS Nexus 連線的情況下，用 `python3 main.py --replay ...` 在本機跑通整個
consumeData() / consumeTPRequest() 邏輯（對應 md 開發流程第 4 步「本機驗證」）。

真正部署到 Edge Server 時，main.py 要改成 `import oneapi` 或官方指定的
package 名稱來源（依 ACS Gemini 上 ONEAPI 手冊為準——這點本機環境查不到，
第一次上機時請對照官方 SDK 確認 import 路徑跟下面各 class 的方法名稱是否一致，
必要時調整 sample.py 對應呼叫）。這裡的方法命名是依照 PROJECT_CONTEXT.md
第 6 節「OneAPI 關鍵 API 速查」表格整理出來的最佳猜測。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DataType(str, Enum):
    PRODUCTION_LOTSTART = "PRODUCTION_LOTSTART"
    PRODUCTION_LOTEND = "PRODUCTION_LOTEND"
    PRODUCTION_WAFERSTART = "PRODUCTION_WAFERSTART"
    PRODUCTION_WAFEREND = "PRODUCTION_WAFEREND"
    PRODUCTION_TESTSTART = "PRODUCTION_TESTSTART"
    PRODUCTION_TESTEND = "PRODUCTION_TESTEND"
    PRODUCTION_TESTFLOWSTART = "PRODUCTION_TESTFLOWSTART"
    PRODUCTION_TESTFLOWEND = "PRODUCTION_TESTFLOWEND"
    PRODUCTION_TESTSUITESTART = "PRODUCTION_TESTSUITESTART"
    PRODUCTION_TESTSUITEEND = "PRODUCTION_TESTSUITEEND"
    MEASURED_PARAMETRIC = "MEASURED_PARAMETRIC"
    MEASURED_FUNCTIONAL = "MEASURED_FUNCTIONAL"
    MEASURED_MULTI_PARAM = "MEASURED_MULTI_PARAM"
    MEASURED_SCAN = "MEASURED_SCAN"
    DEVICE = "DEVICE"
    USERDEFINED = "USERDEFINED"
    DATALOGTEXT = "DATALOGTEXT"


@dataclass
class TestCell:
    testerId: str = "SIM_TESTER_1"
    lot: str | None = None
    wafer: int | None = None


@dataclass
class NexusData:
    """單筆即時事件資料。真正 OneAPI 的 NexusData 介面請以官方手冊為準；
    這裡只放 sample.py 實際用到的欄位，方便本機 replay。"""

    _type: DataType
    test_num: int | None = None
    pin: str | None = None
    value: float | None = None
    site: int | None = None
    x: int | None = None
    y: int | None = None
    sbin: int | None = None
    hbin: int | None = None
    test_time: float | None = None
    extra: dict = field(default_factory=dict)

    def getType(self) -> DataType:
        return self._type


class AppInfo:
    def __init__(self, name: str = "acs-rtdi-app", version: str = "0.1"):
        self.name = name
        self.version = version


class Command:
    def __init__(self, name: str, payload: dict | None = None):
        self.name = name
        self.payload = payload or {}


class Monitor:
    """要繼承並覆寫 consumeData / consumeTPSend / consumeTPRequest。"""

    def consumeData(self, tc: TestCell, data: NexusData) -> None:
        raise NotImplementedError

    def consumeTPSend(self, tc: TestCell, data: str) -> None:
        pass

    def consumeTPRequest(self, tc: TestCell, request: str) -> str:
        raise NotImplementedError


class Interface:
    _monitor: Monitor | None = None
    _connected = False

    @staticmethod
    def connect(me: AppInfo, cmdPort: int = 0, dataPort: int = 0) -> int:
        Interface._connected = True
        print(f"[oneapi_mock] Interface.connect({me.name} v{me.version}) -> OK")
        return 0

    @staticmethod
    def disconnect() -> int:
        Interface._connected = False
        print("[oneapi_mock] Interface.disconnect() -> OK")
        return 0

    @staticmethod
    def registerMonitor(myMonitor: Monitor) -> None:
        Interface._monitor = myMonitor
        print(f"[oneapi_mock] Interface.registerMonitor({type(myMonitor).__name__})")

    @staticmethod
    def getConnectionState(cmdChannel: int) -> None:
        return None

    @staticmethod
    def sendCommand(tc: TestCell, cmd: Command) -> int:
        print(f"[oneapi_mock] Interface.sendCommand(tc={tc.testerId}, cmd={cmd.name}, payload={cmd.payload})")
        return 0


class ActionManager:
    """本機模擬：set_message / set_wait / get 只是把訊息印出來 + 存到記憶體，
    方便 replay harness 之後把結果撈出來檢查/畫報告，不會真的送回 SmarTest。"""

    _pending_wait: dict[str, tuple[int, str]] = {}
    sent_messages: list[dict] = []

    @staticmethod
    def set_message(testerId: str, message: str) -> None:
        print(f"[ActionManager.set_message] tester={testerId}\n{message}\n")
        ActionManager.sent_messages.append({"testerId": testerId, "message": message})

    @staticmethod
    def set_wait(testerId: str, wait: int, message: str) -> None:
        ActionManager._pending_wait[testerId] = (wait, message)

    @staticmethod
    def get(testerId: str) -> str:
        wait, message = ActionManager._pending_wait.pop(testerId, (0, ""))
        return message
