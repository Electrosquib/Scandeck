import sqlite3
import settings

def get_db_connection():
    conn = sqlite3.connect("scanlists.db", timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn

def get_system_data(system_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM systems WHERE id = ?", (system_id,))
    system = dict(cur.fetchone())

    cur.execute("SELECT * FROM sites WHERE system_id = ?", (system_id,))
    sites = [dict(r) for r in cur.fetchall()]

    for s in sites:
        cur.execute("SELECT freq, is_control FROM frequencies WHERE site_id = ?", (s["id"],))
        s["frequencies"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM talkgroups WHERE system_id = ?", (system_id,))
    tgs = [dict(r) for r in cur.fetchall()]

    conn.close()

    return {
        "system": system["name"],
        "system_id": system["id"],
        "sites": sites,
        "talkgroups": tgs
    }

def get_site_frequencies(system_id, site_id, control_only = False):
    conn = get_db_connection()
    cur = conn.cursor()

    if control_only:
        cur.execute("""
        SELECT f.freq
        FROM frequencies f
        JOIN sites s ON f.site_id = s.id
        WHERE s.system_id = ? AND s.id = ? AND f.is_control = 1
        """, (system_id, site_id))
    else:
        cur.execute("""
        SELECT f.freq
        FROM frequencies f
        JOIN sites s ON f.site_id = s.id
        WHERE s.system_id = ? AND s.id = ?
        """, (system_id, site_id))

    freqs = [r[0] for r in cur.fetchall()]
    conn.close()
    return freqs

def make_trunk_file(system_id, site_id):
    conn = get_db_connection()
    cur = conn.cursor()
    freqs = get_site_frequencies(system_id, site_id, control_only=True)
    cur.execute("SELECT name FROM systems WHERE id = ?", (system_id,))
    system_name = cur.fetchone()[0]
    if not freqs:
        return None
    with open(settings.TRUNK_FILE, "w") as f:
        contents = f""""Sysname"	"Control Channel List"	"Offset"	"NAC"	"Modulation"	"TGID Tags File"	"Whitelist"	"Blacklist"	"Center Frequency"
"{system_name}"	"{",".join(str(f) for f in freqs)}"	"0"	"0"	"cqpsk"	""	""	""	"""""
        f.write(contents)
