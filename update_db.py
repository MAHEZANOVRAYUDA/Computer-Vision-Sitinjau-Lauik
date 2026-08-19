import psycopg2
conn = psycopg2.connect(dbname='sitinjau_lauik_db', user='postgres', password='postgres123', host='localhost', port=5432)
cur = conn.cursor()
cur.execute("INSERT INTO gerbang_kamera (id_gerbang, id_ruas, nama_gerbang, arah_menghadap, status_perangkat) VALUES ('gerbang_a_masuk', 1, 'Gerbang A - Masuk', 'ke_padang', 'aktif') ON CONFLICT DO NOTHING;")
cur.execute("INSERT INTO gerbang_kamera (id_gerbang, id_ruas, nama_gerbang, arah_menghadap, status_perangkat) VALUES ('gerbang_b_masuk', 1, 'Gerbang B - Masuk', 'ke_solok', 'aktif') ON CONFLICT DO NOTHING;")
conn.commit()
print("Database updated!")
