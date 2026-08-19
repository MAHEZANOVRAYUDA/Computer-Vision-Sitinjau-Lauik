import cv2

class Visualizer:
    @staticmethod
    def gambar_overlay(frame, hasil_deteksi, daftar_garis, coco_mapping, counter_kumulatif, nama_gerbang="Kamera", tampilkan_garis=True):
        """
        Menggambar garis virtual, bounding box, dan counter di frame
        untuk keperluan visualisasi/debugging saat pengembangan.
        Fungsi ini TIDAK memengaruhi logika penghitungan - murni tampilan.
        """
        # Gambar garis virtual per lajur (bisa disembunyikan via config)
        if tampilkan_garis:
            for garis in daftar_garis:
                warna = (0, 255, 255) if garis.arah == "masuk" else (255, 0, 255)
                cv2.line(
                    frame,
                    tuple(map(int, garis.titik_1)),
                    tuple(map(int, garis.titik_2)),
                    warna,
                    2,
                )
                cv2.putText(
                    frame,
                    f"{garis.line_id} ({garis.arah})",
                    (int(garis.titik_1[0]), int(garis.titik_1[1]) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    warna,
                    2,
                )

        # Gambar bounding box hasil deteksi
        if hasil_deteksi.boxes is not None and hasil_deteksi.boxes.id is not None:
            boxes = hasil_deteksi.boxes.xyxy.cpu().numpy()
            track_ids = hasil_deteksi.boxes.id.cpu().numpy().astype(int)
            class_ids = hasil_deteksi.boxes.cls.cpu().numpy().astype(int)

            for box, tid, cid in zip(boxes, track_ids, class_ids):
                if cid not in coco_mapping:
                    continue
                x1, y1, x2, y2 = map(int, box)
                label = f"{coco_mapping[cid]} #{tid}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
                cv2.putText(
                    frame, label, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2,
                )

        # Panel ringkasan counter di OpenCV dihapus agar tidak duplikat dengan dashboard web.
        # Tampilan teks dan counter sekarang sepenuhnya dikelola oleh UI web (index.html)
        # sehingga video feed lebih bersih dan fokus pada visualisasi bounding box/tracking.

        return frame
