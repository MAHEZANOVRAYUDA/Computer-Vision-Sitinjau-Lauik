import psycopg2
from src.config_loader import load_config
from src.logger import setup_logging, get_logger

setup_logging(level_str="INFO")
logger = get_logger(__name__)

def update_db():
    config = load_config("config/config.yaml")
    db_config = config.get("database", {})
    
    try:
        conn = psycopg2.connect(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 5432),
            database=db_config.get("dbname", "sitinjau_lauik_db"),
            user=db_config.get("user", "postgres"),
            password=db_config.get("password", "postgres123")
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Tambahkan kolom-kolom baru untuk MKJI jika belum ada
        alter_queries = [
            "ALTER TABLE status_ruas ADD COLUMN IF NOT EXISTS volume_smp_jam_mkji FLOAT DEFAULT 0.0;",
            "ALTER TABLE status_ruas ADD COLUMN IF NOT EXISTS kapasitas_smp_jam_mkji FLOAT DEFAULT 1890.0;",
            "ALTER TABLE status_ruas ADD COLUMN IF NOT EXISTS vc_ratio_mkji FLOAT DEFAULT 0.0;",
            "ALTER TABLE status_ruas ADD COLUMN IF NOT EXISTS los_mkji VARCHAR(2) DEFAULT 'A';",
            "ALTER TABLE status_ruas ADD COLUMN IF NOT EXISTS metode_kepadatan VARCHAR(50) DEFAULT 'Sistem Pakar';",
        ]
        
        for q in alter_queries:
            cur.execute(q)
            logger.info(f"Eksekusi: {q}")
            
        logger.info("Database berhasil diperbarui dengan kolom-kolom MKJI!")
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Gagal mengupdate database: {e}")

if __name__ == "__main__":
    update_db()
