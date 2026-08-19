"""
logger.py
==========
Modul logging terpusat untuk seluruh sistem Sitinjau Lauik CV.

Menggantikan semua penggunaan print() di modul lain dengan logging
yang proper: level yang bisa dikonfigurasi, output ke file dengan
rotasi otomatis, dan format timestamp yang konsisten.

Cara pakai di modul lain:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("Sistem siap.")
    logger.warning("Koneksi lambat.")
    logger.error("Gagal baca frame.")
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


# Warna ANSI untuk output terminal (dinonaktifkan jika tidak ada TTY)
_WARNA = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Hijau
    "WARNING":  "\033[33m",   # Kuning
    "ERROR":    "\033[31m",   # Merah
    "CRITICAL": "\033[35m",   # Magenta
    "RESET":    "\033[0m",
}
_PAKAI_WARNA = sys.stdout.isatty()


class _FormatterBerwarna(logging.Formatter):
    """Formatter kustom dengan warna ANSI untuk output terminal."""

    FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        if _PAKAI_WARNA:
            warna = _WARNA.get(record.levelname, "")
            reset = _WARNA["RESET"]
            return f"{warna}{formatted}{reset}"
        return formatted


def setup_logging(
    level_str: str = "INFO",
    log_file_path: str = "data/logs/sistem.log",
) -> None:
    """
    Konfigurasi root logger. Dipanggil SATU KALI di awal program (main.py,
    mqtt_consumer.py, api_server.py). Modul lain cukup panggil get_logger().

    Args:
        level_str: Level logging sebagai string ("DEBUG", "INFO", "WARNING", "ERROR").
        log_file_path: Path file log, relatif terhadap root folder proyek.
    """
    level = getattr(logging, level_str.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Hindari menambahkan handler ganda jika setup_logging dipanggil lebih dari sekali
    if root_logger.handlers:
        return

    formatter = _FormatterBerwarna(
        fmt=_FormatterBerwarna.FORMAT,
        datefmt=_FormatterBerwarna.DATEFMT,
    )

    # --- Handler 1: Console (stdout) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # --- Handler 2: File dengan rotasi tengah malam ---
    try:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = TimedRotatingFileHandler(
            filename=log_path,
            when="midnight",
            backupCount=7,      # Simpan 7 hari terakhir
            encoding="utf-8",
        )
        # File log tanpa warna ANSI
        file_formatter = logging.Formatter(
            fmt=_FormatterBerwarna.FORMAT,
            datefmt=_FormatterBerwarna.DATEFMT,
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Jangan crash hanya karena file log tidak bisa dibuat
        logging.getLogger(__name__).warning(
            f"Tidak bisa membuat file log di '{log_file_path}': {e}. "
            "Logging hanya ke console."
        )

    # Kurangi verbositas library eksternal yang berisik
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("paho.mqtt").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Mengembalikan logger dengan nama modul yang diberikan.
    Gunakan __name__ sebagai argumen untuk nama logger yang konsisten.

    Contoh:
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)
