import psycopg2
conn = psycopg2.connect(dbname='sitinjau_lauik_db', user='postgres', password='postgres123', host='localhost', port=5432)
cur = conn.cursor()
cur.execute("SELECT id_gerbang FROM gerbang_kamera")
print("gerbang_kamera:")
for row in cur.fetchall():
    print(row)
