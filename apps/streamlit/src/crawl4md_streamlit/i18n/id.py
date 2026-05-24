"""Indonesian (id) translations for the crawl4md Streamlit app."""

from __future__ import annotations

from crawl4md_streamlit.i18n._types import Strings

STRINGS_ID: Strings = {
    # ── Page ──────────────────────────────────────────────────────────────
    "PAGE_TITLE": ":material/travel_explore: crawl4md — Perayap Situs Web",
    "PAGE_SUBTITLE": (
        "Arahkan ke situs web mana pun dan crawl4md akan mengikuti tautan, "
        "mengekstrak konten utama dari setiap halaman, dan menyimpan semuanya "
        "sebagai file Markdown yang bersih dan mudah dibaca."
    ),
    "SESSION_PREFIX": "Sesi: {session_id}",
    "SESSION_LOADING": "Memuat sesi browser...",
    "SESSION_SELECTOR_LABEL": "ID Sesi",
    "SESSION_CREATE_BUTTON": "Baru",
    "SESSION_CREATE_BUTTON_TOOLTIP": "Buat sesi terpisah (hasil saat ini tetap tersimpan)",
    "PROGRESS_HEADER": "⏳ Progres",
    "PROGRESS_CAPTION": "Pantau aktivitas crawl secara langsung.",
    "PROGRESS_EXPANDER_LABEL": "Statistik langsung",
    "LANG_SELECTOR_LABEL": "Bahasa",
    # ── Form ──────────────────────────────────────────────────────────────
    "FORM_SUBHEADER": "⚙️ Atur crawl Anda",
    "FORM_CAPTION": (
        "Konfigurasikan URL awal, aturan pemfilteran, dan perilaku crawl sebelum memulai."
    ),
    "FORM_EXPANDER_LABEL": "Pengaturan crawl",
    "FORM_URLS_LABEL": "URL Situs Web",
    "FORM_URLS_HELP": (
        "Tempel satu atau lebih halaman awal. "
        "Gunakan satu baris per situs atau pisahkan dengan koma."
    ),
    "FORM_INCLUDE_PATHS_LABEL": "Hanya sertakan pola URL",
    "FORM_INCLUDE_PATHS_HELP": (
        "Biarkan kosong untuk mengizinkan semua halaman di situs yang sama. "
        "Gunakan pola regex untuk tetap di dalam sebuah bagian."
    ),
    "FORM_EXCLUDE_PATHS_LABEL": "Lewati pola URL",
    "FORM_EXCLUDE_PATHS_HELP": "Halaman yang cocok dengan pola regex ini akan dilewati.",
    "FORM_LIMIT_LABEL": "Batas halaman",
    "FORM_LIMIT_HELP": (
        "Batas penemuan: setelah sejumlah halaman ditemukan, "
        "perayap berhenti menemukan tautan baru tetapi tetap menyelesaikan "
        "semua halaman yang sudah ditemukan."
    ),
    "FORM_DELAY_LABEL": "Jeda antar halaman",
    "FORM_DELAY_HELP": "Memberi jarak awal halaman untuk mengurangi pemblokiran oleh situs web.",
    "FORM_DEPTH_LABEL": "Kedalaman tautan",
    "FORM_DEPTH_HELP": "Seberapa dalam mengikuti tautan.",
    "FORM_RETRIES_LABEL": "Putaran percobaan ulang",
    "FORM_RETRIES_HELP": "Mencoba lagi halaman yang gagal setelah pendinginan.",
    "FORM_OUTPUT_FORMAT_LABEL": "Format keluaran",
    "FORM_OUTPUT_FORMAT_HELP": "Pilih Markdown untuk teks berformat atau TXT untuk teks biasa.",
    "FORM_EXTRACT_MAIN_LABEL": "Ekstrak hanya konten utama",
    "FORM_EXTRACT_MAIN_HELP": (
        "Menyimpan teks artikel/produk dan menghapus sebagian besar menu, footer, dan sidebar."
    ),
    "FORM_ADVANCED_LABEL": "Opsi lanjutan",
    "FORM_FLUSH_LABEL": "Tulis setiap N halaman",
    "FORM_FLUSH_HELP": "Menulis file yang dihasilkan secara berkala selama crawl.",
    "FORM_MAX_FILE_SIZE_LABEL": "Ukuran file maksimum (MB)",
    "FORM_MAX_FILE_SIZE_HELP": "Membagi keluaran menjadi file yang lebih mudah dibuka dan diunduh.",
    "FORM_WAIT_FOR_LABEL": "Tunggu render tambahan",
    "FORM_WAIT_FOR_HELP": ("Membantu halaman berat JavaScript selesai dimuat sebelum ekstraksi."),
    "FORM_TIMEOUT_LABEL": "Batas waktu halaman",
    "FORM_TIMEOUT_HELP": "Maksimum detik untuk memuat satu halaman.",
    "FORM_ACTIVITY_LOG_LABEL": "Entri log aktivitas",
    "FORM_ACTIVITY_LOG_HELP": (
        "Mengontrol berapa banyak entri terbaru yang ditampilkan di panel Log Aktivitas."
    ),
    "FORM_MAX_CONCURRENT_LABEL": "Pengambilan paralel",
    "FORM_MAX_CONCURRENT_HELP": (
        "Mengambil hingga N halaman yang sudah ditemukan secara bersamaan pada "
        "crawl awal. 5 (default) dapat mempercepat crawl besar pada situs yang "
        "permisif. Gunakan 1 untuk situs yang ketat atau mudah terkena batas "
        "laju. Jeda tetap memberi jarak awal "
        "permintaan; retry tetap serial demi keamanan WAF. Risiko: nilai lebih "
        "tinggi meningkatkan kemungkinan dibatasi kecepatannya atau diblokir. "
        "Minimum: 1. Direkomendasikan: 1-5."
    ),
    "FORM_EXCLUDE_TAGS_LABEL": "Tag HTML yang dihapus",
    "FORM_EXCLUDE_TAGS_HELP": (
        "Nilai umum menghapus menu, skrip, formulir, dan gaya dari teks yang diekstrak."
    ),
    "FORM_INCLUDE_ONLY_TAGS_LABEL": "Hanya simpan tag HTML ini",
    "FORM_INCLUDE_ONLY_TAGS_HELP": (
        "Lanjutan: hanya ekstrak konten dari tag HTML ini. Biarkan kosong untuk penggunaan normal."
    ),
    # ── Action buttons ────────────────────────────────────────────────────
    "BTN_START": "Mulai",
    "BTN_STOP": "Hentikan",
    # ── Stop dialog ───────────────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_STOP_BODY": (
        "Hentikan crawl ini sekarang? Ini akan membatalkan halaman yang masih dalam proses."
    ),
    "DIALOG_BTN_KEEP": "Lanjutkan",
    "DIALOG_BTN_STOP": "Hentikan crawl",
    # ── Toast messages ────────────────────────────────────────────────────
    "TOAST_SUCCESS": "{n} halaman berhasil di-crawl",
    "TOAST_FAILED": "{n} halaman gagal di-crawl",
    "TOAST_DISCOVERED": "{n} halaman ditemukan",
    # ── Progress metrics ──────────────────────────────────────────────────
    "METRIC_PROCESSED_LABEL": "📄 Upaya halaman",
    "METRIC_PROCESSED_DELTA": "{n} total",
    "METRIC_PROCESSED_DELTA_RETRY": "{n} upaya retry",
    "METRIC_PROCESSED_TOOLTIP": (
        "Jumlah upaya saat ini untuk fase crawl yang berjalan. Halaman gagal dapat dicoba lagi selama retry."
    ),
    "METRIC_SUCCESSFUL_LABEL": "✅ Berhasil",
    "METRIC_SUCCESSFUL_DELTA": "{n} selesai",
    "METRIC_SUCCESSFUL_TOOLTIP": "Halaman yang berhasil diproses",
    "METRIC_FAILED_LABEL": "❌ Gagal",
    "METRIC_FAILED_DELTA": "{n} gagal",
    "METRIC_FAILED_TOOLTIP": "Halaman yang gagal selama pemrosesan",
    "METRIC_DISCOVERED_LABEL": "🔎 Ditemukan",
    "METRIC_DISCOVERED_DELTA": "{n} ditemukan, {m} tersisa",
    "METRIC_DISCOVERED_TOOLTIP": "URL yang ditemukan dan diantrekan sejauh ini",
    "METRIC_LIMIT_LABEL": "🔢 Batas",
    "METRIC_LIMIT_TOOLTIP": (
        "Batas penemuan — setelah tercapai, URL baru tidak ditambahkan, "
        "tetapi URL yang sudah ditemukan tetap di-crawl."
    ),
    "METRIC_LIMIT_DELTA_REACHED": "Penemuan dihentikan (batas tercapai)",
    "METRIC_LIMIT_DELTA_MORE": "Menemukan lebih banyak halaman",
    "METRIC_STATE_WORD": "Status",
    "METRIC_STATE_DELTA": "Tahap siklus saat ini",
    "METRIC_STATE_TOOLTIP": "Status siklus hidup crawl saat ini",
    # ── Progress bar labels ───────────────────────────────────────────────
    "DENOM_DISCOVERED": "{n} ditemukan",
    "DENOM_LIMIT": "{n} batas",
    "PROGRESS_ATTEMPTS": "{n} upaya",
    "PROGRESS_COMPLETE": "selesai",
    "PROGRESS_RETRYING": "Sedang retry halaman gagal",
    # ── Status line ───────────────────────────────────────────────────────
    "STATUS_CRAWLING": "Merayapi: {url_html}",
    "STATUS_ELAPSED": "Waktu berlalu: {elapsed}",
    "STATUS_NEXT_URL": "Berikutnya: {url_html}",
    "STATUS_ACTIVE_FETCHES": "Pengambilan aktif ({count} dari {max} dikonfigurasi)",
    "STATUS_NEXT_FETCHES": "Berikutnya ({count})",
    "STATUS_MORE_URLS": "+{count} lainnya",
    # ── ETA phrases ───────────────────────────────────────────────────────
    "ETA_ESTIMATING": "Mengestimasi...",
    "ETA_LESS_THAN_MINUTE": "Kurang dari satu menit lagi",
    "ETA_MINUTES": "Sekitar {n} menit lagi",
    "ETA_HOURS_MINUTES": "Sekitar {h}j {m}m lagi",
    # ── State banners ─────────────────────────────────────────────────────
    "BANNER_FAILED": "🔴 Gagal — pemrosesan mengalami kesalahan",
    "BANNER_CANCEL_REQUESTED": "🟡 Penghentian diminta — menunggu worker selesai",
    "BANNER_STOPPED": "🟡 Dihentikan — file yang dihasilkan tetap tersedia",
    # ── Error messages ────────────────────────────────────────────────────
    "ERROR_NO_ACTIVE_CRAWL": "Tidak ada crawl yang aktif untuk dihentikan.",
    "ERROR_CRAWL_ALREADY_RUNNING": "Crawl sudah berjalan di sesi browser ini.",
    "ERROR_SESSION_STORAGE_WRITE": (
        "Penyimpanan browser tidak tersedia. Aktifkan local storage di browser ini lalu "
        "muat ulang halaman."
    ),
    "ERROR_SESSION_FOLDER_MISSING": "Folder sesi tidak ada.",
    "ERROR_CRAWL_FAILED_FALLBACK": "Crawl gagal.",
    "ERROR_PLAYWRIGHT_MISSING": (
        "Binari browser Playwright tidak ada di lingkungan Python ini. "
        "Instal Chromium lalu coba crawl lagi:\n"
        "python -m playwright install chromium"
    ),
    # ── Activity log ──────────────────────────────────────────────────────
    "ACTIVITY_LOG_HEADER": "Log aktivitas",
    # ── Files section ─────────────────────────────────────────────────────
    "FILES_HEADER": "Detail File",
    "FILES_CRAWL_RESULT_LABEL": "📁 Hasil crawl",
    "FILES_DOWNLOADS_SUBHEADER": "🗂️ File Output",
    "FILES_COL_NAME": "File",
    "FILES_COL_TYPE": "Tipe",
    "FILES_COL_SIZE": "Ukuran (MB)",
    "FILES_COL_MODIFIED": "Dimodifikasi",
    "FILES_SESSION_CAPTION": "Folder sesi: {path}",
    "FILES_DOWNLOAD_TOO_LARGE": "{file} terlalu besar untuk diunduh dari aplikasi.",
    "FILES_DOWNLOADS_IN_PROGRESS": "Crawl sedang berjalan — file muncul seiring halaman diproses.",
    "FILES_DOWNLOADS_SUBTITLE": "Pratinjau atau unduh file crawl Anda di bawah ini.",
    "FILES_PREVIEW_BUTTON": ":material/visibility:",
    "FILES_PREVIEW_HELP": "Pratinjau {file}",
    "FILES_PREVIEW_PATH": "Path: {path}",
    "FILES_PREVIEW_SIZE": "Ukuran: {size_kib} KiB",
    "FILES_PREVIEW_MODIFIED_AT": "Terakhir dimodifikasi: {value}",
    "FILES_PREVIEW_CREATED_AT": "Dibuat: {value}",
    "FILES_PREVIEW_UNSUPPORTED": "Pratinjau hanya tersedia untuk file berbasis teks. {file} tidak bisa dipratinjau.",
    "FILES_PREVIEW_MISSING": "File yang dipilih sudah tidak tersedia: {file}",
    "FILES_PREVIEW_READ_ERROR": "Tidak dapat membaca file untuk pratinjau: {file}",
    "FILES_PREVIEW_EMPTY": "{file} kosong.",
    "FILES_PREVIEW_TRUNCATED": "Pratinjau dibatasi pada {limit_kib} KiB pertama.",
    # ── Ready result download ──────────────────────────────────────────
    "READY_RESULT_HEADER": "📦 Hasil crawl siap",
    "READY_RESULT_SINGLE_SUBTITLE": "1 file berhasil siap diunduh",
    "READY_RESULT_ZIP_SUBTITLE": "{count} file berhasil — dikemas dalam satu zip",
    "READY_RESULT_DOWNLOAD_BUTTON": "⬇ Unduh",
    "READY_RESULT_TOO_LARGE": "Output terlalu besar untuk diunduh dari aplikasi — gunakan daftar file di bawah.",
    # ── State display labels ──────────────────────────────────────────────
    "STATE_LABELS": {
        "idle": "Siap",
        "running": "Berjalan",
        "failed": "Gagal",
        "completed": "Selesai",
        "cancel_requested": "Pembatalan Diminta",
        "stopped": "Dihentikan",
    },
}
