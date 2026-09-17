from __future__ import annotations

import base64
import json

import pytest

from print_agent.tsc_print_agent import (
    LABEL_BITMAP_BYTES,
    _normalized_printer_name,
    build_tspl_job,
    decode_label_bitmaps,
    is_origin_allowed,
    load_config,
)


def _payload(bitmap: bytes | None = None) -> dict[str, object]:
    data = bitmap if bitmap is not None else bytes(LABEL_BITMAP_BYTES)
    return {
        "paper_width_mm": 80,
        "paper_height_mm": 60,
        "labels": [
            {
                "width": 640,
                "height": 480,
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
        ],
    }


def test_decode_label_bitmaps_accepts_exact_80_by_60_bitmap() -> None:
    bitmap = bytes([0xAA]) * LABEL_BITMAP_BYTES

    assert decode_label_bitmaps(_payload(bitmap)) == [bitmap]


def test_decode_label_bitmaps_rejects_wrong_bitmap_length() -> None:
    with pytest.raises(ValueError, match="点阵长度不正确"):
        decode_label_bitmaps(_payload(b"too short"))


def test_build_tspl_job_inverts_bitmap_for_black_text_on_white_background() -> None:
    bitmap = bytes([0x55]) * LABEL_BITMAP_BYTES

    job = build_tspl_job([bitmap], gap_mm=2, direction=1)

    assert job.startswith(
        b"SIZE 80 mm,60 mm\r\nGAP 2 mm,0 mm\r\nDIRECTION 1\r\nREFERENCE 0,0\r\nCLS\r\n"
        b"BITMAP 0,0,80,480,0,"
    )
    assert bytes([0xAA]) * LABEL_BITMAP_BYTES in job
    assert job.endswith(b"\r\nPRINT 1,1\r\n")


def test_build_tspl_job_can_keep_original_bitmap_polarity() -> None:
    bitmap = bytes([0x55]) * LABEL_BITMAP_BYTES

    job = build_tspl_job([bitmap], gap_mm=2, direction=1, invert_bitmap=False)

    assert bitmap in job


def test_origin_policy_allows_configured_and_private_origins() -> None:
    configured = frozenset({"https://platform.hedespace.com"})

    assert is_origin_allowed("https://platform.hedespace.com", configured)
    assert is_origin_allowed("http://192.168.10.80:3001", configured)
    assert is_origin_allowed("http://localhost:3001", configured)
    assert not is_origin_allowed("https://example.com", configured)


def test_load_config_reads_windows_service_json(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "printer_name": "TSC Test Printer",
                "port": 18121,
                "gap_mm": 3,
                "direction": 0,
                "invert_bitmap": False,
                "allowed_origins": ["https://print.example.com"],
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "TSC_PRINTER_NAME",
        "TSC_PRINT_AGENT_PORT",
        "TSC_LABEL_GAP_MM",
        "TSC_PRINT_DIRECTION",
        "HEDE_PRINT_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(config_path)

    assert config.printer_name == "TSC Test Printer"
    assert config.port == 18121
    assert config.gap_mm == 3
    assert config.direction == 0
    assert config.invert_bitmap is False
    assert config.allowed_origins == frozenset({"https://print.example.com"})


def test_environment_overrides_windows_service_json(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TSC_PRINTER_NAME", "Environment Printer")
    monkeypatch.setenv("TSC_PRINT_AGENT_PORT", "18122")

    config = load_config(config_path)

    assert config.printer_name == "Environment Printer"
    assert config.port == 18122


def test_printer_name_normalization_ignores_spaces_and_punctuation() -> None:
    assert _normalized_printer_name("TSCTTP-244 Pro") == _normalized_printer_name(
        "TSC TTP 244-Pro"
    )
