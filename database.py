# -*- coding: utf-8 -*-
"""
KlikStudio - lapisan database & aturan bisnis (SQLite).

Berisi 6 entitas sesuai ERD: ADMIN, PELANGGAN, PAKET_FOTO, JADWAL_STUDIO,
BOOKING, dan NOTA_ANTREAN (+ tabel kecil PENGATURAN untuk jam operasional).
File ini TIDAK memakai Streamlit, jadi aturan bisnis bisa diuji terpisah.
"""
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "klikstudio_app.db"

# ------------------------------------------------------------------ konstanta
STATUS_BOOKING = ["Menunggu", "Dikonfirmasi", "Selesai", "Dibatalkan"]
STATUS_AKTIF = ("Menunggu", "Dikonfirmasi")          # status yang menahan slot
TRANSISI = {                                          # perubahan status yang boleh
    "Menunggu": ["Dikonfirmasi", "Dibatalkan"],
    "Dikonfirmasi": ["Selesai", "Dibatalkan"],
    "Selesai": [],
    "Dibatalkan": [],
}
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (
    id_admin       INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_admin TEXT NOT NULL,
    nama           TEXT
);
CREATE TABLE IF NOT EXISTS pelanggan (
    id_pelanggan   INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_pelanggan TEXT NOT NULL,
    no_telepon     TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS paket_foto (
    id_paket     INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_paket   TEXT NOT NULL,
    durasi_sesi  INTEGER NOT NULL CHECK (durasi_sesi > 0),
    harga        INTEGER NOT NULL CHECK (harga >= 0)
);
CREATE TABLE IF NOT EXISTS jadwal_studio (
    id_jadwal     INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal       TEXT NOT NULL,
    jam_mulai     TEXT NOT NULL,
    jam_selesai   TEXT NOT NULL,
    status_jadwal TEXT NOT NULL DEFAULT 'Tersedia'
                  CHECK (status_jadwal IN ('Tersedia','Terpesan','Nonaktif')),
    id_admin      INTEGER REFERENCES admin(id_admin)
);
CREATE TABLE IF NOT EXISTS booking (
    id_booking     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_admin       INTEGER NOT NULL REFERENCES admin(id_admin),
    id_pelanggan   INTEGER NOT NULL REFERENCES pelanggan(id_pelanggan),
    id_paket       INTEGER NOT NULL REFERENCES paket_foto(id_paket),
    id_jadwal      INTEGER NOT NULL REFERENCES jadwal_studio(id_jadwal),
    status_booking TEXT NOT NULL DEFAULT 'Menunggu'
                   CHECK (status_booking IN ('Menunggu','Dikonfirmasi','Selesai','Dibatalkan')),
    dibuat_pada    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS nota_antrean (
    id_nota         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_booking      INTEGER NOT NULL UNIQUE REFERENCES booking(id_booking),
    nomor_antrean   INTEGER NOT NULL,
    tanggal_antrean TEXT NOT NULL,
    waktu_terbit    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (tanggal_antrean, nomor_antrean)
);
CREATE TABLE IF NOT EXISTS pengaturan (
    kunci TEXT PRIMARY KEY,
    nilai TEXT NOT NULL
);
"""

BOOKING_SQL = """
SELECT b.id_booking, b.status_booking, b.id_pelanggan, b.id_paket, b.id_jadwal,
       p.nama_pelanggan, p.no_telepon,
       f.nama_paket, f.durasi_sesi, f.harga,
       j.tanggal, j.jam_mulai, j.jam_selesai,
       n.id_nota, n.nomor_antrean, n.tanggal_antrean, n.waktu_terbit
FROM booking b
JOIN pelanggan p     ON p.id_pelanggan = b.id_pelanggan
JOIN paket_foto f    ON f.id_paket     = b.id_paket
JOIN jadwal_studio j ON j.id_jadwal    = b.id_jadwal
LEFT JOIN nota_antrean n ON n.id_booking = b.id_booking
"""


# ------------------------------------------------------------------ util
def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(menit: int) -> str:
    return f"{menit // 60:02d}:{menit % 60:02d}"


def fmt_jam(hhmm: str) -> str:
    """'10:00' -> '10.00' (gaya penulisan di presentasi)."""
    return hhmm.replace(":", ".")


def overlap(a1: int, a2: int, b1: int, b2: int) -> bool:
    """Dua rentang bertabrakan jika jam mulai salah satunya < jam selesai yang lain."""
    return a1 < b2 and b1 < a2


def rupiah(n) -> str:
    return "Rp " + f"{int(n):,}".replace(",", ".")


def tgl_id(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def hari_tgl_id(d: date) -> str:
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year}"


def norm_phone(raw: str) -> str:
    """Ambil angka saja; awalan 62 / +62 diubah menjadi 0."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    return digits


# ------------------------------------------------------------------ koneksi
@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows(sql, params=()):
    with db() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


# ------------------------------------------------------------------ pengaturan
DEFAULT_SETTINGS = {"buka": "09:00", "tutup": "17:00", "durasi": "60", "jeda": "15"}


def get_settings() -> dict:
    data = {r["kunci"]: r["nilai"] for r in rows("SELECT * FROM pengaturan")}
    cfg = {**DEFAULT_SETTINGS, **data}
    return {"buka": cfg["buka"], "tutup": cfg["tutup"],
            "durasi": int(cfg["durasi"]), "jeda": int(cfg["jeda"])}


def save_settings(buka: str, tutup: str, durasi: int, jeda: int):
    with db() as con:
        for k, v in {"buka": buka, "tutup": tutup, "durasi": durasi, "jeda": jeda}.items():
            con.execute("INSERT OR REPLACE INTO pengaturan (kunci, nilai) VALUES (?,?)", (k, str(v)))


# ------------------------------------------------------------------ slot
def buat_slot(con, tanggal: str, buka: int, tutup: int, durasi: int, jeda: int):
    """Bentuk slot dari jam operasional. Slot yang beririsan dengan slot lama dilewati."""
    ada = [(to_min(r["jam_mulai"]), to_min(r["jam_selesai"])) for r in con.execute(
        "SELECT jam_mulai, jam_selesai FROM jadwal_studio WHERE tanggal=?", (tanggal,))]
    dibuat = dilewati = 0
    mulai = buka
    while durasi > 0 and mulai + durasi <= tutup:
        selesai = mulai + durasi
        if any(overlap(mulai, selesai, a, b) for a, b in ada):
            dilewati += 1
        else:
            con.execute("INSERT INTO jadwal_studio (tanggal, jam_mulai, jam_selesai, id_admin) "
                        "VALUES (?,?,?,1)", (tanggal, to_hhmm(mulai), to_hhmm(selesai)))
            ada.append((mulai, selesai))
            dibuat += 1
        mulai = selesai + jeda
    return dibuat, dilewati


def buat_slot_rentang(tgl_awal: date, tgl_akhir: date, buka: str, tutup: str, durasi: int, jeda: int):
    if to_min(tutup) <= to_min(buka):
        return False, "Jam tutup harus lebih besar dari jam buka.", 0, 0
    if (tgl_akhir - tgl_awal).days > 62:
        return False, "Rentang tanggal maksimal 63 hari.", 0, 0
    total_dibuat = total_lewat = 0
    with db() as con:
        d = tgl_awal
        while d <= tgl_akhir:
            a, b = buat_slot(con, d.isoformat(), to_min(buka), to_min(tutup), durasi, jeda)
            total_dibuat += a
            total_lewat += b
            d += timedelta(days=1)
    save_settings(buka, tutup, durasi, jeda)
    return True, "ok", total_dibuat, total_lewat


def tambah_slot_manual(tanggal: str, mulai: str, selesai: str):
    if to_min(selesai) <= to_min(mulai):
        return False, "Jam selesai harus lebih besar dari jam mulai."
    with db() as con:
        for r in con.execute("SELECT jam_mulai, jam_selesai FROM jadwal_studio WHERE tanggal=?", (tanggal,)):
            if overlap(to_min(mulai), to_min(selesai), to_min(r["jam_mulai"]), to_min(r["jam_selesai"])):
                return False, (f"Ditolak: bertabrakan dengan slot {fmt_jam(r['jam_mulai'])}-"
                               f"{fmt_jam(r['jam_selesai'])} pada tanggal yang sama.")
        con.execute("INSERT INTO jadwal_studio (tanggal, jam_mulai, jam_selesai, id_admin) VALUES (?,?,?,1)",
                    (tanggal, mulai, selesai))
    return True, "Slot manual ditambahkan."


def toggle_slot(id_jadwal: int):
    with db() as con:
        s = con.execute("SELECT status_jadwal FROM jadwal_studio WHERE id_jadwal=?", (id_jadwal,)).fetchone()
        if not s:
            return False, "Slot tidak ditemukan."
        if s[0] == "Terpesan":
            return False, "Slot sedang terpesan. Batalkan booking-nya dulu."
        baru = "Nonaktif" if s[0] == "Tersedia" else "Tersedia"
        con.execute("UPDATE jadwal_studio SET status_jadwal=? WHERE id_jadwal=?", (baru, id_jadwal))
    return True, f"Slot sekarang berstatus {baru}."


def hapus_slot(id_jadwal: int):
    with db() as con:
        if con.execute("SELECT 1 FROM booking WHERE id_jadwal=?", (id_jadwal,)).fetchone():
            return False, "Slot punya riwayat booking, tidak bisa dihapus. Nonaktifkan saja."
        con.execute("DELETE FROM jadwal_studio WHERE id_jadwal=?", (id_jadwal,))
    return True, "Slot dihapus."


def set_tanggal(tanggal: str, buka: bool):
    """Buka / tutup satu tanggal sekaligus (slot terpesan tidak disentuh)."""
    dari, ke = ("Nonaktif", "Tersedia") if buka else ("Tersedia", "Nonaktif")
    with db() as con:
        cur = con.execute("UPDATE jadwal_studio SET status_jadwal=? WHERE tanggal=? AND status_jadwal=?",
                          (ke, tanggal, dari))
    return cur.rowcount


def bentrok(con, id_jadwal: int, abaikan_booking: int = None) -> bool:
    """True bila slot beririsan dengan booking aktif lain pada tanggal yang sama."""
    s = con.execute("SELECT tanggal, jam_mulai, jam_selesai FROM jadwal_studio WHERE id_jadwal=?",
                    (id_jadwal,)).fetchone()
    q = ("SELECT 1 FROM booking b JOIN jadwal_studio j ON j.id_jadwal=b.id_jadwal "
         "WHERE j.tanggal=? AND b.status_booking IN ('Menunggu','Dikonfirmasi') "
         "AND j.jam_mulai < ? AND ? < j.jam_selesai AND b.id_jadwal != ?")
    params = [s["tanggal"], s["jam_selesai"], s["jam_mulai"], id_jadwal]
    if abaikan_booking:
        q += " AND b.id_booking != ?"
        params.append(abaikan_booking)
    return con.execute(q, params).fetchone() is not None


def slot_tersedia(tanggal: str, durasi_paket: int):
    """Slot Tersedia yang cukup untuk durasi paket dan tidak bentrok dengan booking lain."""
    hasil = []
    with db() as con:
        for s in con.execute("SELECT * FROM jadwal_studio WHERE tanggal=? AND status_jadwal='Tersedia' "
                             "ORDER BY jam_mulai", (tanggal,)).fetchall():
            durasi_slot = to_min(s["jam_selesai"]) - to_min(s["jam_mulai"])
            if durasi_slot >= durasi_paket and not bentrok(con, s["id_jadwal"]):
                hasil.append(dict(s))
    return hasil


def tanggal_berikut_tersedia(dari: str, durasi_paket: int, maks_hari: int = 30):
    d = datetime.strptime(dari, "%Y-%m-%d").date()
    for i in range(1, maks_hari + 1):
        t = (d + timedelta(days=i)).isoformat()
        if slot_tersedia(t, durasi_paket):
            return t
    return None


# ------------------------------------------------------------------ pelanggan
def cari_pelanggan(telepon: str):
    return one("SELECT * FROM pelanggan WHERE no_telepon=?", (telepon,)) if telepon else None


def _pelanggan_upsert(con, nama: str, telepon: str) -> int:
    r = con.execute("SELECT id_pelanggan, nama_pelanggan FROM pelanggan WHERE no_telepon=?",
                    (telepon,)).fetchone()
    if r:
        if nama and nama != r["nama_pelanggan"]:
            con.execute("UPDATE pelanggan SET nama_pelanggan=? WHERE id_pelanggan=?",
                        (nama, r["id_pelanggan"]))
        return r["id_pelanggan"]
    return con.execute("INSERT INTO pelanggan (nama_pelanggan, no_telepon) VALUES (?,?)",
                       (nama, telepon)).lastrowid


def _validasi_pelanggan(nama: str, telepon: str):
    if not nama.strip():
        return "Nama pelanggan wajib diisi."
    if len(telepon) < 9 or len(telepon) > 15:
        return "Nomor telepon tidak valid (9-15 angka)."
    return None


# ------------------------------------------------------------------ nota
def terbitkan_nota(con, id_booking: int) -> int:
    ada = con.execute("SELECT id_nota FROM nota_antrean WHERE id_booking=?", (id_booking,)).fetchone()
    if ada:
        return ada[0]
    tgl = con.execute("SELECT j.tanggal FROM booking b JOIN jadwal_studio j ON j.id_jadwal=b.id_jadwal "
                      "WHERE b.id_booking=?", (id_booking,)).fetchone()[0]
    # nomor dimulai dari 1 pada setiap TANGGAL BOOKING (bukan tanggal tombol ditekan)
    nomor = con.execute("SELECT COALESCE(MAX(nomor_antrean),0)+1 FROM nota_antrean WHERE tanggal_antrean=?",
                        (tgl,)).fetchone()[0]
    return con.execute("INSERT INTO nota_antrean (id_booking, nomor_antrean, tanggal_antrean) VALUES (?,?,?)",
                       (id_booking, nomor, tgl)).lastrowid


def nota_txt(b: dict) -> str:
    garis = "=" * 34
    return "\n".join([
        garis, "          KLIK STUDIO", "      Nota Antrean Digital", garis,
        f"Nomor Antrean : {int(b['nomor_antrean']):03d}",
        f"Tanggal       : {tgl_id(b['tanggal'])}",
        f"Jam           : {fmt_jam(b['jam_mulai'])} - {fmt_jam(b['jam_selesai'])}",
        f"Nama          : {b['nama_pelanggan']}",
        f"Telepon       : {b['no_telepon']}",
        f"Paket         : {b['nama_paket']} ({b['durasi_sesi']} menit)",
        f"Harga         : {rupiah(b['harga'])}",
        f"ID Booking    : {b['id_booking']}",
        f"Status        : {b['status_booking']}",
        f"Diterbitkan   : {b['waktu_terbit']}",
        garis, "Tunjukkan nota ini saat datang ke studio.", "Terima kasih sudah memilih KlikStudio!", garis,
    ])


# ------------------------------------------------------------------ booking
def simpan_booking(nama: str, telepon: str, id_paket: int, id_jadwal: int, konfirmasi: bool):
    nama = (nama or "").strip()
    telepon = norm_phone(telepon)
    err = _validasi_pelanggan(nama, telepon)
    if err:
        return False, err, None
    with db() as con:
        slot = con.execute("SELECT * FROM jadwal_studio WHERE id_jadwal=?", (id_jadwal,)).fetchone()
        paket = con.execute("SELECT * FROM paket_foto WHERE id_paket=?", (id_paket,)).fetchone()
        if not slot or not paket:
            return False, "Slot atau paket tidak ditemukan.", None
        if slot["status_jadwal"] != "Tersedia":
            return False, "Ditolak: slot sudah tidak tersedia.", None
        if to_min(slot["jam_selesai"]) - to_min(slot["jam_mulai"]) < paket["durasi_sesi"]:
            return False, f"Ditolak: slot belum cukup untuk durasi {paket['durasi_sesi']} menit.", None
        if bentrok(con, id_jadwal):
            return False, "Ditolak: jadwal bertabrakan dengan booking lain.", None
        id_pel = _pelanggan_upsert(con, nama, telepon)
        id_b = con.execute("INSERT INTO booking (id_admin, id_pelanggan, id_paket, id_jadwal, status_booking) "
                           "VALUES (1,?,?,?, 'Menunggu')", (id_pel, id_paket, id_jadwal)).lastrowid
        con.execute("UPDATE jadwal_studio SET status_jadwal='Terpesan' WHERE id_jadwal=?", (id_jadwal,))
        if konfirmasi:
            terbitkan_nota(con, id_b)
            con.execute("UPDATE booking SET status_booking='Dikonfirmasi' WHERE id_booking=?", (id_b,))
    msg = "Booking disimpan & dikonfirmasi. Nota antrean terbit." if konfirmasi \
        else "Booking disimpan dengan status Menunggu (belum ada nota)."
    return True, msg, id_b


def ubah_status(id_booking: int, baru: str):
    with db() as con:
        b = con.execute("SELECT * FROM booking WHERE id_booking=?", (id_booking,)).fetchone()
        if not b:
            return False, "Booking tidak ditemukan."
        lama = b["status_booking"]
        if baru == lama:
            return False, f"Booking sudah berstatus {lama}."
        if baru not in TRANSISI[lama]:
            if lama == "Menunggu" and baru == "Selesai":
                return False, "Ditolak sistem: booking Menunggu tidak boleh langsung Selesai. Konfirmasi dulu."
            if not TRANSISI[lama]:
                return False, f"Ditolak sistem: booking {lama} sudah final dan tidak bisa diubah."
            return False, f"Ditolak sistem: {lama} tidak bisa langsung menjadi {baru}."
        if baru == "Dikonfirmasi":
            terbitkan_nota(con, id_booking)
        if baru == "Dibatalkan":                      # pembatalan melepas slot
            con.execute("UPDATE jadwal_studio SET status_jadwal='Tersedia' WHERE id_jadwal=?", (b["id_jadwal"],))
        con.execute("UPDATE booking SET status_booking=? WHERE id_booking=?", (baru, id_booking))
    pesan = {"Dikonfirmasi": "Booking dikonfirmasi, nota antrean diterbitkan.",
             "Selesai": "Booking ditandai Selesai.",
             "Dibatalkan": "Booking dibatalkan, slot dilepas dan bisa dipesan kembali."}
    return True, pesan[baru]


def edit_booking(id_booking: int, nama: str, telepon: str, id_paket: int):
    nama, telepon = (nama or "").strip(), norm_phone(telepon)
    err = _validasi_pelanggan(nama, telepon)
    if err:
        return False, err
    with db() as con:
        b = con.execute(BOOKING_SQL + " WHERE b.id_booking=?", (id_booking,)).fetchone()
        if not b or b["status_booking"] not in STATUS_AKTIF:
            return False, "Hanya booking Menunggu / Dikonfirmasi yang bisa diedit."
        paket = con.execute("SELECT * FROM paket_foto WHERE id_paket=?", (id_paket,)).fetchone()
        if to_min(b["jam_selesai"]) - to_min(b["jam_mulai"]) < paket["durasi_sesi"]:
            return False, "Ditolak: slot booking ini tidak cukup untuk durasi paket yang dipilih."
        id_pel = _pelanggan_upsert(con, nama, telepon)
        con.execute("UPDATE booking SET id_pelanggan=?, id_paket=? WHERE id_booking=?",
                    (id_pel, id_paket, id_booking))
    return True, "Perubahan booking disimpan."


def hapus_booking(id_booking: int):
    with db() as con:
        b = con.execute("SELECT id_jadwal FROM booking WHERE id_booking=?", (id_booking,)).fetchone()
        if not b:
            return False, "Booking tidak ditemukan."
        con.execute("DELETE FROM nota_antrean WHERE id_booking=?", (id_booking,))
        con.execute("DELETE FROM booking WHERE id_booking=?", (id_booking,))
        con.execute("UPDATE jadwal_studio SET status_jadwal='Tersedia' WHERE id_jadwal=? "
                    "AND status_jadwal='Terpesan'", (b["id_jadwal"],))
    return True, "Booking dihapus dan slot dilepas."


def get_booking(id_booking: int):
    return one(BOOKING_SQL + " WHERE b.id_booking=?", (id_booking,))


def list_booking(where: str = "", params=()):
    return rows(BOOKING_SQL + (" WHERE " + where if where else "") + " ORDER BY j.tanggal DESC, j.jam_mulai", params)


# ------------------------------------------------------------------ paket foto
def simpan_paket(nama: str, durasi: int, harga: int, id_paket: int = None):
    nama = (nama or "").strip()
    if not nama:
        return False, "Nama paket wajib diisi."
    with db() as con:
        if id_paket:
            con.execute("UPDATE paket_foto SET nama_paket=?, durasi_sesi=?, harga=? WHERE id_paket=?",
                        (nama, durasi, harga, id_paket))
            return True, "Paket diperbarui."
        con.execute("INSERT INTO paket_foto (nama_paket, durasi_sesi, harga) VALUES (?,?,?)",
                    (nama, durasi, harga))
    return True, "Paket ditambahkan."


def hapus_paket(id_paket: int):
    with db() as con:
        if con.execute("SELECT 1 FROM booking WHERE id_paket=?", (id_paket,)).fetchone():
            return False, "Paket sudah dipakai di booking, tidak bisa dihapus."
        con.execute("DELETE FROM paket_foto WHERE id_paket=?", (id_paket,))
    return True, "Paket dihapus."


# ------------------------------------------------------------------ inisialisasi
def init_db(seed_contoh: bool = True):
    with db() as con:
        con.executescript(SCHEMA)
        # Tidak ada login: satu admin bawaan dipakai sebagai pencatat booking (FK id_admin).
        if con.execute("SELECT COUNT(*) FROM admin").fetchone()[0] == 0:
            con.execute("INSERT INTO admin (username, password_admin, nama) VALUES ('admin','-','Admin KlikStudio')")
        if con.execute("SELECT COUNT(*) FROM paket_foto").fetchone()[0] == 0:
            con.executemany("INSERT INTO paket_foto (nama_paket, durasi_sesi, harga) VALUES (?,?,?)",
                            [("Paket Solo", 30, 150000), ("Paket Couple", 60, 300000),
                             ("Paket Family", 60, 450000)])
        if seed_contoh and con.execute("SELECT COUNT(*) FROM jadwal_studio").fetchone()[0] == 0:
            cfg = DEFAULT_SETTINGS
            hari_ini = date.today()
            for i in range(7):
                buat_slot(con, (hari_ini + timedelta(days=i)).isoformat(), to_min(cfg["buka"]),
                          to_min(cfg["tutup"]), int(cfg["durasi"]), int(cfg["jeda"]))
    if seed_contoh and not rows("SELECT 1 FROM booking LIMIT 1"):
        _seed_contoh()


def _seed_contoh():
    """Data contoh seperti di presentasi: Rina (Couple) & Dimas (Solo) masih Menunggu."""
    t = date.today().isoformat()
    slots = rows("SELECT * FROM jadwal_studio WHERE tanggal=? ORDER BY jam_mulai", (t,))
    paket = {p["nama_paket"]: p["id_paket"] for p in rows("SELECT * FROM paket_foto")}
    if len(slots) >= 4:
        simpan_booking("Rina Wulandari", "081234567801", paket["Paket Couple"], slots[1]["id_jadwal"], False)
        simpan_booking("Dimas Prakoso", "081234567802", paket["Paket Solo"], slots[2]["id_jadwal"], False)
        simpan_booking("Salsa Amelia", "081234567803", paket["Paket Family"], slots[0]["id_jadwal"], True)
