# KlikStudio - Booking Foto (Streamlit)

## Cara menjalankan (VS Code)
1. Buka folder ini di VS Code, lalu buka terminal.
2. (Opsional) buat virtual env:  python -m venv venv  ->  venv\Scripts\activate  (Windows) / source venv/bin/activate (Mac/Linux)
3. pip install -r requirements.txt
4. streamlit run app.py

Database SQLite (klikstudio_app.db) dibuat otomatis saat pertama dijalankan.
Hapus file itu untuk reset data. Ubah SEED_CONTOH = False di app.py kalau tidak mau data contoh.

## Struktur
- app.py        : tampilan (Streamlit)
- database.py   : database SQLite + aturan bisnis (slot, bentrok jadwal, status, nota)
- assets/       : logo KlikStudio
- .streamlit/config.toml : tema terang
