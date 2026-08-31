import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.api_server import app, db

client = TestClient(app)

def test_kendaraan_per_jenis():
    # Mock data from database
    mock_data = {
        "gerbang_a_masuk": {"motor": 70, "mobil": 371},
        "gerbang_a_keluar": {"motor": 40, "mobil": 146},
        "gerbang_b_masuk": {"bus": 45, "truk": 65},
        "gerbang_b_keluar": {"bus": 36, "truk": 77}
    }
    
    with patch("src.api_server.db") as mock_db:
        mock_db.ambil_kumulatif_masuk_keluar_per_gerbang.return_value = mock_data
        
        response = client.get("/api/kendaraan-per-jenis")
        assert response.status_code == 200
        
        data = response.json()
        assert "per_gerbang" in data
        assert "gerbang_a" in data["per_gerbang"]
        assert "gerbang_b" in data["per_gerbang"]
        assert "total_gabungan" in data
        assert "total_masuk_hari_ini" in data
        
        # Verify specific numbers
        assert data["per_gerbang"]["gerbang_a"]["motor"]["masuk"] == 70
        assert data["per_gerbang"]["gerbang_a"]["motor"]["keluar"] == 40
        assert data["total_gabungan"]["mobil"]["masuk"] == 371
        
        total_masuk = 70 + 371 + 45 + 65
        assert data["total_masuk_hari_ini"] == total_masuk
