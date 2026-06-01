"""Indonesian (id) translations for the crawl4md Streamlit app."""

from __future__ import annotations

from crawl4md_streamlit.i18n._types import Strings

STRINGS_ID: Strings = {
    # ── Page ──────────────────────────────────────────────────────────────
    "PAGE_TITLE": ":material/travel_explore: Langkah 1 - Jelajahi Situs Web",
    "PAGE_SUBTITLE": (
        "Arahkan ke situs web mana pun dan crawl4md akan mengikuti tautan, "
        "mengekstrak konten utama dari setiap halaman, dan menyimpan semuanya "
        "sebagai file Markdown yang bersih dan mudah dibaca."
    ),
    "SESSION_PREFIX": "Sesi: {session_id}",
    "SESSION_LOADING": "Memuat sesi browser...",
    "SESSION_SELECTOR_LABEL": "ID Sesi",
    "SESSION_EXPIRY_CAPTION": "Sesi ini akan kedaluwarsa dalam {days} hari \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_SINGULAR": "Sesi ini akan kedaluwarsa dalam 1 hari \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOURS": "Sesi ini akan kedaluwarsa dalam {days} hari dan {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAY_HOURS": "Sesi ini akan kedaluwarsa dalam 1 hari dan {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOUR": "Sesi ini akan kedaluwarsa dalam {days} hari dan 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAY_HOUR": "Sesi ini akan kedaluwarsa dalam 1 hari dan 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_HOURS": "Sesi ini akan kedaluwarsa dalam {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR": "Sesi ini akan kedaluwarsa dalam 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_SOON": "Sesi ini akan segera kedaluwarsa \u2014 semua file akan dihapus.",
    "SESSION_CREATE_BUTTON": "Baru",
    "SESSION_CREATE_BUTTON_TOOLTIP": "Buat sesi terpisah (hasil saat ini tetap tersimpan)",
    "SESSION_LOAD_BUTTON_TOOLTIP": "Muat sesi yang ada berdasarkan ID",
    "SESSION_EXTEND_BUTTON_TOOLTIP": "Perpanjang sesi — memberikan hingga 7 hari dari sekarang",
    "PROGRESS_HEADER": "⏳ Progres",
    "PROGRESS_CAPTION": "Pantau aktivitas crawl secara langsung.",
    "PROGRESS_EXPANDER_LABEL": "Statistik langsung",
    "PROGRESS_EXPANDER_LABEL_ACTIVE": "Statistik langsung: {crawl_id}",
    "LANG_SELECTOR_LABEL": "Bahasa",
    "NAV_CRAWL": "1. Crawl",
    "NAV_VECTOR_INDEX": "2. Vector Index",
    "NAV_SEMANTIC_SEARCH": "3. Semantic Search",
    "NAV_RAG_QA": "4. RAG Q&A",
    "NAV_CONVERSATIONAL_RAG": "5. Conversational RAG",
    "PAGE_VECTOR_INDEX_TITLE": ":material/database: Langkah 2 - Bangun Vector Index",
    "PAGE_VECTOR_INDEX_SUBTITLE": (
        "Pilih output Markdown, teks, atau ZIP, pecah menjadi chunk, buat embedding, "
        "dan simpan di vector database."
    ),
    "PAGE_SEMANTIC_SEARCH_TITLE": ":material/search: Langkah 3 - Semantic Search",
    "PAGE_SEMANTIC_SEARCH_SUBTITLE": (
        "Ubah kueri pencarian menjadi embedding, ambil chunk yang mirip, dan tinjau "
        "hasil berperingkat dari vector database."
    ),
    "PAGE_RAG_QA_TITLE": ":material/question_answer: Langkah 4 - Tanya Jawab RAG",
    "PAGE_RAG_QA_SUBTITLE": (
        "Ajukan satu pertanyaan, ambil konteks, susun prompt, dan tinjau jawaban LLM "
        "beserta sumbernya."
    ),
    "PAGE_CONVERSATIONAL_RAG_TITLE": ":material/forum: Langkah 5 - Conversational RAG",
    "PAGE_CONVERSATIONAL_RAG_SUBTITLE": (
        "Chat lintas giliran dengan konteks hasil retrieval, riwayat percakapan, dan "
        "penulisan ulang kueri."
    ),
    "PLACEHOLDER_SECTION_HEADER": "Area kerja langkah",
    "PLACEHOLDER_SECTION_CAPTION": (
        "Halaman ini memakai kontrol sesi dan layout yang sama sambil backend RAG ditambahkan."
    ),
    "PLACEHOLDER_EXPANDER_LABEL": "Ringkasan kebutuhan",
    "PLACEHOLDER_VECTOR_INDEX": (
        "Pilih file Markdown atau teks yang dihasilkan, termasuk arsip ZIP yang berisi file "
        "tersebut. Alur berikutnya akan memecah konten menjadi chunk, membuat embedding, "
        "dan menyimpan index di ChromaDB."
    ),
    "PLACEHOLDER_SEMANTIC_SEARCH": (
        "Masukkan kueri pencarian, buat embedding dengan model yang sama seperti chunk dalam "
        "index, jalankan similarity search, lalu tampilkan snippet berperingkat dengan skor "
        "dan referensi sumber."
    ),
    "PLACEHOLDER_RAG_QA": (
        "Ajukan satu pertanyaan, ambil chunk yang paling relevan, gabungkan ke dalam prompt, "
        "panggil LLM yang dipilih, lalu tampilkan jawaban bersama sumber konteks."
    ),
    "PLACEHOLDER_CONVERSATIONAL_RAG": (
        "Gunakan antarmuka chat yang dapat menulis ulang kueri retrieval dari konteks "
        "percakapan, menyertakan riwayat pesan terbaru, dan berkembang menjadi alur RAG "
        "dengan memory."
    ),
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
    # ── Load session dialog ───────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_LOAD_SESSION_ID_LABEL": "ID Sesi",
    "DIALOG_LOAD_SESSION_ID_PLACEHOLDER": "Tempel ID sesi di sini",
    "DIALOG_LOAD_SESSION_ID_HELP": "Masukkan ID sesi dari browser atau komputer lain",
    "DIALOG_LOAD_BTN_CANCEL": "Batal",
    "DIALOG_LOAD_BTN_LOAD": "Muat",
    "DIALOG_LOAD_SESSION_NOT_FOUND": "Sesi '{id}' tidak ditemukan di server ini.",
    "DIALOG_LOAD_SESSION_ALREADY_LOADED": "Sesi '{id}' sudah tersedia. Beralih ke sesi tersebut.",
    "DIALOG_LOAD_SESSION_INVALID_ID": "ID sesi tidak valid.",
    # ── Toast messages ────────────────────────────────────────────────────
    "TOAST_SUCCESS": "{n} halaman berhasil di-crawl",
    "TOAST_FAILED": "{n} halaman gagal di-crawl",
    "TOAST_DISCOVERED": "{n} halaman ditemukan",
    "TOAST_SESSION_CREATED": "Sesi baru berhasil dibuat",
    "TOAST_SESSION_LOADED": "Sesi '{id}' berhasil dimuat.",
    "TOAST_SESSION_EXTENDED": "Sesi diperpanjang — masa berlaku diperbarui ke 7 hari",
    "TOAST_SESSION_EXTEND_FAILED": "Sesi gagal diperpanjang",
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
    # ── Progress charts ───────────────────────────────────────────────────
    "CHART_CUMULATIVE_TITLE": "Total crawl kumulatif dari waktu ke waktu",
    "CHART_CUMULATIVE_TITLE_SECOND": "Total crawl per detik",
    "CHART_CUMULATIVE_TITLE_MINUTE": "Linimasa kemajuan crawl",
    "CHART_CUMULATIVE_TITLE_HOUR": "Total crawl per jam",
    "CHART_SERIES_LIMIT": "Batas",
    "CHART_SERIES_DISCOVERED": "Ditemukan",
    "CHART_SERIES_SUCCESSFUL": "Berhasil",
    "CHART_SERIES_FAILED": "Gagal",
    "CHART_TIME_UNIT_SECOND": "detik",
    "CHART_TIME_UNIT_MINUTE": "menit",
    "CHART_TIME_UNIT_HOUR": "jam",
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
    # ── Portfolio footer ─────────────────────────────────────────────────
    "FOOTER_BUILT_BY": "Dibuat oleh {author}",
    "FOOTER_TAGLINE": "Playground crawl-to-RAG dengan bantuan AI",
    "FOOTER_LINK_LINKEDIN": "LinkedIn",
    "FOOTER_LINK_GITHUB": "GitHub",
    "FOOTER_LINK_README": "Baca dokumentasi",
    "FOOTER_LINK_STREAMLIT_README": "Panduan app",
    # ── Portfolio modal ──────────────────────────────────────────────────
    "PORTFOLIO_MODAL_TITLE": "Hai, saya {author}",
    "PORTFOLIO_MODAL_BODY": (
        "Saya membangun proyek ini sebagai RAG playground berbasis eksperimen "
        "langsung dengan bantuan AI. Saat ini aplikasinya bisa meng-crawl situs "
        "web dan mengubah halaman menjadi Markdown yang rapi. Berikutnya, saya "
        "akan menambahkan vector embeddings, semantic search, tanya jawab RAG, "
        "dan eksperimen conversational RAG."
    ),
    "PORTFOLIO_MODAL_CTA": (
        "Kalau proyek ini menarik atau berguna, mari terhubung di LinkedIn atau "
        "beri star di repo GitHub. Saya senang berbagi progres dan bertukar catatan."
    ),
    "PORTFOLIO_MODAL_LINK_LINKEDIN": "Terhubung di LinkedIn",
    "PORTFOLIO_MODAL_LINK_GITHUB": "Beri star repo GitHub",
    "PORTFOLIO_MODAL_LINK_README": "Baca dokumentasi",
    "PORTFOLIO_MODAL_LINK_STREAMLIT_README": "Panduan developer app",
    "PORTFOLIO_MODAL_CLOSE_LABEL": "Tutup",
    "PORTFOLIO_MODAL_PHOTO_ALT": "Foto profil {author}",
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
