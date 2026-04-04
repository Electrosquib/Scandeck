import sqlite3

conn = sqlite3.connect("scanlists.db")
cur = conn.cursor()

cur.execute("PRAGMA foreign_keys = ON")

cur.execute("""
CREATE TABLE IF NOT EXISTS systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    list_type TEXT DEFAULT 'trunked'
)
""")

columns = [row[1] for row in cur.execute("PRAGMA table_info(systems)").fetchall()]
if "list_type" not in columns:
    cur.execute("ALTER TABLE systems ADD COLUMN list_type TEXT DEFAULT 'trunked'")
    cur.execute("UPDATE systems SET list_type = 'trunked' WHERE list_type IS NULL OR list_type = ''")

cur.execute("""
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER,
    rfss INTEGER,
    site_dec INTEGER,
    site_hex TEXT,
    nac TEXT,
    description TEXT,
    county TEXT,
    lat REAL,
    lon REAL,
    range_km REAL,
    FOREIGN KEY (system_id) REFERENCES systems(id) ON DELETE CASCADE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS frequencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER,
    freq REAL,
    is_control INTEGER,
    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS talkgroups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER,
    decimal INTEGER,
    hex TEXT,
    alpha TEXT,
    mode TEXT,
    description TEXT,
    tag TEXT,
    category TEXT,
    FOREIGN KEY (system_id) REFERENCES systems(id) ON DELETE CASCADE
)
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_sites_system ON sites(system_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_freq_site ON frequencies(site_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_tg_system ON talkgroups(system_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_tg_decimal ON talkgroups(decimal)")

conn.commit()
conn.close()
