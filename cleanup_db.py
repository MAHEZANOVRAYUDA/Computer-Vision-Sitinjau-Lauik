import psycopg2

conn = psycopg2.connect(dbname='sitinjau_lauik_db', user='postgres', password='postgres123', host='localhost', port=5432)
cur = conn.cursor()

# Hapus hitungan_kendaraan yang merujuk ke gerbang_a_masuk atau gerbang_b_masuk
cur.execute("DELETE FROM hitungan_kendaraan WHERE id_gerbang IN ('gerbang_a_masuk', 'gerbang_b_masuk', 'gerbang_a_keluar', 'gerbang_b_keluar');")

# Hapus dari gerbang_kamera
cur.execute("DELETE FROM gerbang_kamera WHERE id_gerbang IN ('gerbang_a_masuk', 'gerbang_b_masuk', 'gerbang_a_keluar', 'gerbang_b_keluar');")

conn.commit()
print("Database cleaned up!")
