"""
config_loader.py
=================
Modul utilitas untuk memuat file config.yaml menjadi objek Python
yang mudah diakses. Semua modul lain mengimpor dari sini agar
konfigurasi hanya dibaca dari SATU sumber (config/config.yaml).

Changelog v2 (Blueprint Perbaikan):
- Tambah compute_kapasitas() yang menghitung KVR dari parameter dasar
  ruas jalan di section ruas_jalan config — tidak lagi hardcode angka
  kapasitas. Dipanggil otomatis saat load_config().
- Tulis WARNING ke logger jika kapasitas terhitung berbeda dari nilai
  yang mungkin tersimpan di field lama (sistem_pakar.kapasitas_meter_lajur)
  supaya ketahuan kalau ada nilai lama yang tidak sinkron.
"""

import logging
import yaml
import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

from src.sistem_pakar import hitung_kapasitas_volumetrik_ruas

# Gunakan logger standar Python (bukan src.logger) karena config_loader
# diimport SEBELUM setup_logging() dipanggil — hindari circular dependency
_loader_log = logging.getLogger(__name__)


class Config:
    """
    Wrapper sederhana di atas dict hasil parsing YAML,
    supaya bisa diakses baik lewat config["model"]["device"]
    maupun config.get("model.device") (dot notation).
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """
        Ambil nilai dengan dot notation, misalnya:
            config.get("model.confidence_threshold")
            config.get("sistem_pakar.ambang_lancar")

        Catatan: hanya mendukung satu level nesting per segmen dot.
        Untuk nested key seperti "a.b.c", data harus berupa
        {"a": {"b": {"c": value}}} — setiap segmen adalah dict.
        """
        keys = dotted_key.split(".")
        value: Any = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def raw(self) -> Dict[str, Any]:
        return self._data


def _compute_kapasitas(config: Config) -> float:
    """
    Menghitung kapasitas volumetrik ruas dari parameter dasar di config.
    Dipanggil satu kali saat startup.

    Membaca section ruas_jalan dari config.yaml:
        ruas_jalan:
          panjang_meter: 16500
          pct_segmen_sempit: 0.65
          pct_segmen_lebar:  0.35
          kapasitas_lateral_sempit: 2
          kapasitas_lateral_lebar:  6

    Jika section ruas_jalan tidak ada (backward compat), fallback ke
    nilai lama di sistem_pakar.kapasitas_meter_lajur, atau default 56100.

    Returns:
        kapasitas volumetrik ruas (float) dalam satuan meter-lajur
    """
    panjang = config.get("ruas_jalan.panjang_meter")
    pct_sempit = config.get("ruas_jalan.pct_segmen_sempit")
    pct_lebar = config.get("ruas_jalan.pct_segmen_lebar")

    if panjang is not None and pct_sempit is not None and pct_lebar is not None:
        kapasitas_lat_sempit = config.get("ruas_jalan.kapasitas_lateral_sempit", 2.0)
        kapasitas_lat_lebar = config.get("ruas_jalan.kapasitas_lateral_lebar", 6.0)
        kapasitas_hitung = hitung_kapasitas_volumetrik_ruas(
            panjang_meter=float(panjang),
            pct_segmen_sempit=float(pct_sempit),
            pct_segmen_lebar=float(pct_lebar),
            kapasitas_lateral_sempit=float(kapasitas_lat_sempit),
            kapasitas_lateral_lebar=float(kapasitas_lat_lebar),
        )

        # Bandingkan dengan nilai lama jika ada — tulis warning jika berbeda signifikan
        kapasitas_lama = config.get("sistem_pakar.kapasitas_meter_lajur")
        if kapasitas_lama is not None:
            kapasitas_lama_f = float(kapasitas_lama)
            selisih_pct = abs(kapasitas_hitung - kapasitas_lama_f) / max(kapasitas_lama_f, 1) * 100
            if selisih_pct > 0.01:  # toleransi 0.01% untuk floating point
                _loader_log.warning(
                    f"[Config] Kapasitas terhitung dari ruas_jalan ({kapasitas_hitung:.2f}) "
                    f"BERBEDA dengan nilai lama sistem_pakar.kapasitas_meter_lajur "
                    f"({kapasitas_lama_f:.2f}, selisih {selisih_pct:.2f}%). "
                    "Pastikan nilai di config.yaml konsisten!"
                )
            else:
                _loader_log.debug(
                    f"[Config] Kapasitas volumetrik ruas = {kapasitas_hitung:.2f} "
                    f"(dihitung dari ruas_jalan, konsisten dengan nilai lama)."
                )

        return kapasitas_hitung

    # Fallback ke nilai lama
    kapasitas_lama = config.get("sistem_pakar.kapasitas_meter_lajur")
    if kapasitas_lama is not None:
        _loader_log.info(
            f"[Config] Section ruas_jalan tidak lengkap — menggunakan "
            f"sistem_pakar.kapasitas_meter_lajur = {kapasitas_lama} (nilai lama)."
        )
        return float(kapasitas_lama)

    # Last resort default
    _loader_log.warning(
        "[Config] Tidak ada konfigurasi kapasitas ditemukan! "
        "Menggunakan default 56100 (data dosen Sitinjau Lauik). "
        "Tambahkan section ruas_jalan ke config.yaml untuk kalkulasi otomatis."
    )
    return 56100.0


def load_config(path: str = "config/config.yaml") -> Config:
    """
    Memuat file YAML dari path yang diberikan dan menghitung kapasitas
    volumetrik ruas secara otomatis dari parameter dasar di section ruas_jalan.

    Path relatif dihitung dari direktori tempat script dijalankan,
    jadi pastikan Anda menjalankan script dari root folder proyek.

    Setelah load, config akan memiliki key tambahan:
        config.get("kapasitas_meter_lajur_computed")
    yang berisi hasil kalkulasi (bukan nilai lama dari config mentah).
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"File konfigurasi tidak ditemukan di: {config_path.resolve()}\n"
            f"Pastikan Anda menjalankan script dari root folder proyek "
            f"(folder yang berisi folder 'config/')."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    config = Config(data)

    # Hitung kapasitas dan simpan ke objek config untuk diakses semua modul
    kapasitas = _compute_kapasitas(config)
    config._data["kapasitas_meter_lajur_computed"] = kapasitas

    return config
