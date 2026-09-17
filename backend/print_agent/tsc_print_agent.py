from __future__ import annotations

import base64
import binascii
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


DEFAULT_PRINTER_NAME = "TSCTTP-244 Pro"
DEFAULT_PORT = 18120
LABEL_WIDTH_MM = 80.0
LABEL_HEIGHT_MM = 60.0
LABEL_WIDTH_DOTS = 640
LABEL_HEIGHT_DOTS = 480
LABEL_ROW_BYTES = LABEL_WIDTH_DOTS // 8
LABEL_BITMAP_BYTES = LABEL_ROW_BYTES * LABEL_HEIGHT_DOTS
MAX_LABELS_PER_REQUEST = 1_000
MAX_REQUEST_BYTES = 64 * 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = (
    "https://platform.hedespace.com",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
)
SERVICE_NAME = "HedePrintAgent"
SERVICE_DISPLAY_NAME = "Hede 鞋盒标签打印服务"
SERVICE_DESCRIPTION = "接收 Hede 系统鞋盒标签并发送到本机 TSC 打印机。"
CONFIG_FILE_NAME = "config.json"


@dataclass(frozen=True)
class AgentConfig:
    printer_name: str
    port: int
    gap_mm: float
    direction: int
    invert_bitmap: bool
    allowed_origins: frozenset[str]


def _config_int(name: str, value: Any, default: int, minimum: int, maximum: int) -> int:
    raw_value = str(value).strip() if value is not None else ""
    try:
        value = int(raw_value) if raw_value else default
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def _config_float(name: str, value: Any, default: float, minimum: float, maximum: float) -> float:
    raw_value = str(value).strip() if value is not None else ""
    try:
        value = float(raw_value) if raw_value else default
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def _config_bool(name: str, value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是 true 或 false")


def _default_config_path() -> Path:
    configured_path = os.getenv("HEDE_PRINT_AGENT_CONFIG", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    if getattr(sys, "frozen", False):
        sibling_path = Path(sys.executable).resolve().with_name("HedePrintAgent.config.json")
        if sibling_path.exists():
            return sibling_path
    program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / SERVICE_NAME / CONFIG_FILE_NAME


def _read_config_file(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取配置文件 {config_path}：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件 {config_path} 必须是 JSON 对象")
    return payload


def load_config(config_path: str | Path | None = None) -> AgentConfig:
    payload = _read_config_file(Path(config_path) if config_path else _default_config_path())
    origins_value = os.getenv("HEDE_PRINT_ALLOWED_ORIGINS")
    if origins_value is None:
        configured_origins_value = payload.get("allowed_origins", DEFAULT_ALLOWED_ORIGINS)
        if isinstance(configured_origins_value, str):
            origin_values = configured_origins_value.split(",")
        elif isinstance(configured_origins_value, (list, tuple)):
            origin_values = configured_origins_value
        else:
            raise ValueError("allowed_origins 必须是字符串数组")
    else:
        origin_values = origins_value.split(",")
    configured_origins = {
        str(value).strip().rstrip("/")
        for value in origin_values
        if str(value).strip()
    }
    printer_name = os.getenv("TSC_PRINTER_NAME")
    if printer_name is None:
        printer_name = str(payload.get("printer_name", DEFAULT_PRINTER_NAME))
    return AgentConfig(
        printer_name=printer_name.strip() or DEFAULT_PRINTER_NAME,
        port=_config_int(
            "TSC_PRINT_AGENT_PORT",
            os.getenv("TSC_PRINT_AGENT_PORT", payload.get("port")),
            DEFAULT_PORT,
            1,
            65_535,
        ),
        gap_mm=_config_float(
            "TSC_LABEL_GAP_MM",
            os.getenv("TSC_LABEL_GAP_MM", payload.get("gap_mm")),
            2.0,
            0.0,
            20.0,
        ),
        direction=_config_int(
            "TSC_PRINT_DIRECTION",
            os.getenv("TSC_PRINT_DIRECTION", payload.get("direction")),
            1,
            0,
            1,
        ),
        invert_bitmap=_config_bool(
            "TSC_INVERT_BITMAP",
            os.getenv("TSC_INVERT_BITMAP", payload.get("invert_bitmap")),
            True,
        ),
        allowed_origins=frozenset(configured_origins or DEFAULT_ALLOWED_ORIGINS),
    )


def is_origin_allowed(origin: str | None, configured_origins: frozenset[str]) -> bool:
    if not origin:
        return True
    normalized = origin.strip().rstrip("/")
    if normalized in configured_origins:
        return True
    try:
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.hostname == "localhost":
            return True
        return ipaddress.ip_address(parsed.hostname).is_private
    except ValueError:
        return False


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 格式不正确")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 格式不正确") from exc


def decode_label_bitmaps(payload: Any) -> list[bytes]:
    if not isinstance(payload, dict):
        raise ValueError("请求内容必须是 JSON 对象")
    paper_width = _number(payload.get("paper_width_mm"), "paper_width_mm")
    paper_height = _number(payload.get("paper_height_mm"), "paper_height_mm")
    if abs(paper_width - LABEL_WIDTH_MM) > 0.01 or abs(paper_height - LABEL_HEIGHT_MM) > 0.01:
        raise ValueError("打印服务当前仅支持 80×60 mm 鞋盒标签")

    labels = payload.get("labels")
    if not isinstance(labels, list) or not labels:
        raise ValueError("没有可打印的标签")
    if len(labels) > MAX_LABELS_PER_REQUEST:
        raise ValueError(f"单次最多打印 {MAX_LABELS_PER_REQUEST} 张标签")

    decoded_labels: list[bytes] = []
    for index, label in enumerate(labels, start=1):
        if not isinstance(label, dict):
            raise ValueError(f"第 {index} 张标签格式不正确")
        if label.get("width") != LABEL_WIDTH_DOTS or label.get("height") != LABEL_HEIGHT_DOTS:
            raise ValueError(f"第 {index} 张标签必须是 640×480 点阵")
        encoded = label.get("data_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError(f"第 {index} 张标签没有点阵数据")
        try:
            bitmap = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"第 {index} 张标签的点阵编码无效") from exc
        if len(bitmap) != LABEL_BITMAP_BYTES:
            raise ValueError(
                f"第 {index} 张标签点阵长度不正确，应为 {LABEL_BITMAP_BYTES} 字节"
            )
        decoded_labels.append(bitmap)
    return decoded_labels


def _format_mm(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_tspl_job(
    bitmaps: list[bytes],
    *,
    gap_mm: float,
    direction: int,
    invert_bitmap: bool = True,
) -> bytes:
    commands: list[bytes] = []
    for bitmap in bitmaps:
        if len(bitmap) != LABEL_BITMAP_BYTES:
            raise ValueError("标签点阵长度不正确")
        printer_bitmap = bytes(value ^ 0xFF for value in bitmap) if invert_bitmap else bitmap
        commands.extend(
            [
                b"SIZE 80 mm,60 mm\r\n",
                f"GAP {_format_mm(gap_mm)} mm,0 mm\r\n".encode("ascii"),
                f"DIRECTION {direction}\r\n".encode("ascii"),
                b"REFERENCE 0,0\r\n",
                b"CLS\r\n",
                b"BITMAP 0,0,80,480,0,",
                printer_bitmap,
                b"\r\nPRINT 1,1\r\n",
            ]
        )
    return b"".join(commands)


class DOC_INFO_1W(ctypes.Structure):
    _fields_ = [
        ("pDocName", wintypes.LPWSTR),
        ("pOutputFile", wintypes.LPWSTR),
        ("pDatatype", wintypes.LPWSTR),
    ]


class PRINTER_INFO_4W(ctypes.Structure):
    _fields_ = [
        ("pPrinterName", wintypes.LPWSTR),
        ("pServerName", wintypes.LPWSTR),
        ("Attributes", wintypes.DWORD),
    ]


PRINTER_ENUM_LOCAL = 0x00000002
PRINTER_ENUM_CONNECTIONS = 0x00000004
ERROR_INSUFFICIENT_BUFFER = 122


def _load_winspool():
    if os.name != "nt":
        raise OSError("Hede 打印服务只能运行在 Windows 上")
    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    winspool.OpenPrinterW.restype = wintypes.BOOL
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.restype = wintypes.BOOL
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    winspool.StartDocPrinterW.restype = wintypes.DWORD
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.restype = wintypes.BOOL
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndPagePrinter.restype = wintypes.BOOL
    winspool.WritePrinter.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    winspool.WritePrinter.restype = wintypes.BOOL
    winspool.EnumPrintersW.argtypes = [
        wintypes.DWORD,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    winspool.EnumPrintersW.restype = wintypes.BOOL
    return winspool


def _raise_last_windows_error(action: str) -> None:
    error_code = ctypes.get_last_error()
    if error_code:
        detail = ctypes.FormatError(error_code).strip()
        raise OSError(error_code, f"{action}失败：{detail}")
    raise OSError(f"{action}失败")


def list_visible_printers() -> list[str]:
    winspool = _load_winspool()
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    bytes_needed = wintypes.DWORD()
    printers_returned = wintypes.DWORD()
    winspool.EnumPrintersW(
        flags,
        None,
        4,
        None,
        0,
        ctypes.byref(bytes_needed),
        ctypes.byref(printers_returned),
    )
    error_code = ctypes.get_last_error()
    if not bytes_needed.value:
        if error_code not in {0, ERROR_INSUFFICIENT_BUFFER}:
            _raise_last_windows_error("枚举打印机")
        return []

    buffer = ctypes.create_string_buffer(bytes_needed.value)
    if not winspool.EnumPrintersW(
        flags,
        None,
        4,
        ctypes.cast(buffer, ctypes.c_void_p),
        bytes_needed.value,
        ctypes.byref(bytes_needed),
        ctypes.byref(printers_returned),
    ):
        _raise_last_windows_error("枚举打印机")
    printers = ctypes.cast(buffer, ctypes.POINTER(PRINTER_INFO_4W))
    return sorted(
        {
            printers[index].pPrinterName.strip()
            for index in range(printers_returned.value)
            if printers[index].pPrinterName and printers[index].pPrinterName.strip()
        },
        key=str.casefold,
    )


def _normalized_printer_name(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", value.casefold())


def check_printer(printer_name: str) -> str:
    winspool = _load_winspool()
    printer_handle = wintypes.HANDLE()
    if winspool.OpenPrinterW(printer_name, ctypes.byref(printer_handle), None):
        winspool.ClosePrinter(printer_handle)
        return printer_name

    first_error_code = ctypes.get_last_error()
    first_error_detail = (
        ctypes.FormatError(first_error_code).strip() if first_error_code else "未知错误"
    )
    visible_printers = list_visible_printers()
    configured_normalized = _normalized_printer_name(printer_name)
    candidates = [
        name
        for name in visible_printers
        if name.casefold() == printer_name.casefold()
        or _normalized_printer_name(name) == configured_normalized
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.casefold() in seen:
            continue
        seen.add(candidate.casefold())
        printer_handle = wintypes.HANDLE()
        if winspool.OpenPrinterW(candidate, ctypes.byref(printer_handle), None):
            winspool.ClosePrinter(printer_handle)
            return candidate
    raise OSError(
        first_error_code,
        f"打开打印机 {printer_name} 失败：{first_error_detail}",
    )


def send_raw_to_printer(printer_name: str, payload: bytes) -> None:
    winspool = _load_winspool()
    printer_handle = wintypes.HANDLE()
    document_started = False
    page_started = False
    if not winspool.OpenPrinterW(printer_name, ctypes.byref(printer_handle), None):
        _raise_last_windows_error(f"打开打印机 {printer_name}")
    try:
        document_info = DOC_INFO_1W("Hede 鞋盒标签", None, "RAW")
        if not winspool.StartDocPrinterW(printer_handle, 1, ctypes.byref(document_info)):
            _raise_last_windows_error("创建打印任务")
        document_started = True
        if not winspool.StartPagePrinter(printer_handle):
            _raise_last_windows_error("开始打印页面")
        page_started = True

        buffer = ctypes.create_string_buffer(payload)
        bytes_written = wintypes.DWORD()
        if not winspool.WritePrinter(
            printer_handle,
            ctypes.cast(buffer, ctypes.c_void_p),
            len(payload),
            ctypes.byref(bytes_written),
        ):
            _raise_last_windows_error("写入打印数据")
        if bytes_written.value != len(payload):
            raise OSError(f"打印数据未完整写入：{bytes_written.value}/{len(payload)} 字节")
    finally:
        if page_started:
            winspool.EndPagePrinter(printer_handle)
        if document_started:
            winspool.EndDocPrinter(printer_handle)
        winspool.ClosePrinter(printer_handle)


class PrintAgentServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], config: AgentConfig):
        super().__init__(server_address, PrintAgentHandler)
        self.config = config


class PrintAgentHandler(BaseHTTPRequestHandler):
    server: PrintAgentServer
    protocol_version = "HTTP/1.1"
    server_version = "HedePrintAgent/1.0"

    def _origin(self) -> str | None:
        return self.headers.get("Origin")

    def _origin_allowed(self) -> bool:
        return is_origin_allowed(self._origin(), self.server.config.allowed_origins)

    def _cors_headers(self) -> dict[str, str]:
        origin = self._origin()
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Private-Network": "true",
            "Vary": "Origin, Access-Control-Request-Private-Network",
        }
        if origin and self._origin_allowed():
            headers["Access-Control-Allow-Origin"] = origin
        return headers

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in self._cors_headers().items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _reject_disallowed_origin(self) -> bool:
        if self._origin_allowed():
            return False
        self._send_json(403, {"ok": False, "error": "当前网页来源不允许使用本机打印服务"})
        return True

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._reject_disallowed_origin():
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        for name, value in self._cors_headers().items():
            self.send_header(name, value)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_disallowed_origin():
            return
        if self.path != "/health":
            self._send_json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            resolved_printer = check_printer(self.server.config.printer_name)
        except OSError as exc:
            try:
                visible_printers = list_visible_printers()
            except OSError:
                visible_printers = []
            logging.getLogger(SERVICE_NAME).warning(
                "打印机检查失败，配置=%s，可见打印机=%s，错误=%s",
                self.server.config.printer_name,
                visible_printers,
                exc,
            )
            self._send_json(
                503,
                {
                    "ok": False,
                    "printer": self.server.config.printer_name,
                    "error": str(exc),
                    "visible_printers": visible_printers,
                },
            )
            return
        self._send_json(
            200,
            {
                "ok": True,
                "printer": resolved_printer,
                "configured_printer": self.server.config.printer_name,
                "status": "ready",
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_disallowed_origin():
            return
        if self.path != "/print":
            self._send_json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "Content-Length 格式不正确"})
            return
        if content_length <= 0:
            self._send_json(400, {"ok": False, "error": "请求内容为空"})
            return
        if content_length > MAX_REQUEST_BYTES:
            self._send_json(413, {"ok": False, "error": "打印数据过大"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            bitmaps = decode_label_bitmaps(payload)
            raw_job = build_tspl_job(
                bitmaps,
                gap_mm=self.server.config.gap_mm,
                direction=self.server.config.direction,
                invert_bitmap=self.server.config.invert_bitmap,
            )
            resolved_printer = check_printer(self.server.config.printer_name)
            send_raw_to_printer(resolved_printer, raw_job)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "请求不是有效的 JSON"})
            return
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except OSError as exc:
            logging.getLogger(SERVICE_NAME).exception("打印任务失败：%s", exc)
            self._send_json(503, {"ok": False, "error": str(exc)})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "printed": len(bitmaps),
                "printer": resolved_printer,
            },
        )

    def log_message(self, message_format: str, *args: object) -> None:
        logging.getLogger(SERVICE_NAME).info(
            "%s %s", self.client_address[0], message_format % args
        )


def _default_log_path() -> Path:
    program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / SERVICE_NAME / "logs" / "service.log"


def configure_logging(*, service_mode: bool) -> logging.Logger:
    logger = logging.getLogger(SERVICE_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if service_mode:
        log_path = _default_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def create_server(config: AgentConfig) -> PrintAgentServer:
    return PrintAgentServer(("127.0.0.1", config.port), config)


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_STOPPED = 0x00000001
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004
SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004
SERVICE_CONTROL_STOP = 0x00000001
SERVICE_CONTROL_SHUTDOWN = 0x00000005
NO_ERROR = 0
ERROR_FAILED_SERVICE_CONTROLLER_CONNECT = 1063

SERVICE_MAIN_FUNCTION = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))
HANDLER_FUNCTION = ctypes.WINFUNCTYPE(None, wintypes.DWORD)


class SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", wintypes.LPWSTR),
        ("lpServiceProc", SERVICE_MAIN_FUNCTION),
    ]


class WindowsServiceHost:
    def __init__(self) -> None:
        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._status_handle = wintypes.HANDLE()
        self._server: PrintAgentServer | None = None
        self._stopping = threading.Event()
        self._service_main_callback = SERVICE_MAIN_FUNCTION(self._service_main)
        self._control_handler_callback = HANDLER_FUNCTION(self._control_handler)
        self._configure_api()

    def _configure_api(self) -> None:
        self._advapi32.StartServiceCtrlDispatcherW.argtypes = [
            ctypes.POINTER(SERVICE_TABLE_ENTRY)
        ]
        self._advapi32.StartServiceCtrlDispatcherW.restype = wintypes.BOOL
        self._advapi32.RegisterServiceCtrlHandlerW.argtypes = [
            wintypes.LPWSTR,
            HANDLER_FUNCTION,
        ]
        self._advapi32.RegisterServiceCtrlHandlerW.restype = wintypes.HANDLE
        self._advapi32.SetServiceStatus.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SERVICE_STATUS),
        ]
        self._advapi32.SetServiceStatus.restype = wintypes.BOOL

    def _set_status(
        self,
        state: int,
        *,
        controls: int = 0,
        exit_code: int = NO_ERROR,
        wait_hint: int = 0,
    ) -> None:
        if not self._status_handle:
            return
        status = SERVICE_STATUS(
            SERVICE_WIN32_OWN_PROCESS,
            state,
            controls,
            exit_code,
            0,
            0,
            wait_hint,
        )
        self._advapi32.SetServiceStatus(self._status_handle, ctypes.byref(status))

    def _control_handler(self, control_code: int) -> None:
        if control_code not in {SERVICE_CONTROL_STOP, SERVICE_CONTROL_SHUTDOWN}:
            return
        self._set_status(SERVICE_STOP_PENDING, wait_hint=10_000)
        self._stopping.set()
        server = self._server
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()

    def _service_main(self, _argc: int, _argv: ctypes.POINTER(wintypes.LPWSTR)) -> None:
        logger = configure_logging(service_mode=True)
        self._status_handle = self._advapi32.RegisterServiceCtrlHandlerW(
            SERVICE_NAME,
            self._control_handler_callback,
        )
        if not self._status_handle:
            logger.error("注册 Windows 服务控制器失败：%s", ctypes.get_last_error())
            return
        self._set_status(SERVICE_START_PENDING, wait_hint=10_000)
        exit_code = NO_ERROR
        try:
            config = load_config()
            self._server = create_server(config)
            logger.info(
                "服务启动，打印机=%s，地址=127.0.0.1:%s，标签=80x60mm，间隙=%smm，反色=%s",
                config.printer_name,
                config.port,
                _format_mm(config.gap_mm),
                config.invert_bitmap,
            )
            self._set_status(
                SERVICE_RUNNING,
                controls=SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN,
            )
            self._server.serve_forever()
        except Exception:
            exit_code = 1
            logger.exception("打印服务运行失败")
        finally:
            if self._server is not None:
                self._server.server_close()
            logger.info("打印服务已停止")
            self._set_status(SERVICE_STOPPED, exit_code=exit_code)

    def run(self) -> None:
        service_table = (SERVICE_TABLE_ENTRY * 2)(
            SERVICE_TABLE_ENTRY(SERVICE_NAME, self._service_main_callback),
            SERVICE_TABLE_ENTRY(None, SERVICE_MAIN_FUNCTION()),
        )
        if self._advapi32.StartServiceCtrlDispatcherW(service_table):
            return
        error_code = ctypes.get_last_error()
        if error_code == ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
            raise SystemExit("该参数只能由 Windows 服务控制器启动，请先运行安装脚本。")
        _raise_last_windows_error("连接 Windows 服务控制器")


def run_console() -> None:
    logger = configure_logging(service_mode=False)
    try:
        config = load_config()
    except ValueError as exc:
        raise SystemExit(f"配置错误：{exc}") from exc

    logger.info("Hede 本机打印服务")
    logger.info("打印机：%s", config.printer_name)
    logger.info("标签：80×60 mm，间隙：%s mm", _format_mm(config.gap_mm))
    logger.info("地址：http://127.0.0.1:%s", config.port)
    server = create_server(config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("打印服务已停止")
    finally:
        server.server_close()


def main() -> None:
    if "--service" in sys.argv[1:]:
        if os.name != "nt":
            raise SystemExit("Windows 服务模式只能在 Windows 上运行。")
        WindowsServiceHost().run()
        return
    run_console()


if __name__ == "__main__":
    main()
