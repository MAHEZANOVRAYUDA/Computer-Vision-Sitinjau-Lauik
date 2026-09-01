import cv2

class Visualizer:
    @staticmethod
    def gambar_overlay(frame, hasil_deteksi, daftar_garis, coco_mapping, counter_kumulatif, nama_gerbang="Kamera", tampilkan_garis=True):
        """
        Menggambar garis virtual, bounding box, dan counter di frame
        untuk keperluan visualisasi/debugging saat pengembangan.
        Fungsi ini TIDAK memengaruhi logika penghitungan - murni tampilan.
        """
        # Gambar bounding box hasil deteksi
        if tampilkan_garis and hasil_deteksi.boxes is not None and hasil_deteksi.boxes.id is not None:
            boxes = hasil_deteksi.boxes.xyxy.cpu().numpy()
            track_ids = hasil_deteksi.boxes.id.cpu().numpy().astype(int)
            class_ids = hasil_deteksi.boxes.cls.cpu().numpy().astype(int)

            for box, tid, cid in zip(boxes, track_ids, class_ids):
                if cid not in coco_mapping:
                    continue
                x1, y1, x2, y2 = map(int, box)
                label = f"{coco_mapping[cid]} #{tid}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 1)
                cv2.putText(
                    frame, label, (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1,
                )

        # Panel ringkasan counter di OpenCV dihapus agar tidak duplikat dengan dashboard web.
        # Tampilan teks dan counter sekarang sepenuhnya dikelola oleh UI web (index.html)
        # sehingga video feed lebih bersih dan fokus pada visualisasi bounding box/tracking.

        return frame
