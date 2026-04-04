from flask import Flask, render_template, request, jsonify, redirect, url_for
import csv
from io import StringIO
import os
import shutil
import sqlite3

app = Flask(__name__)

BASE_DIR = "/home/scandeck-one/Scandeck/Scan Lists"
DB_PATH = "scanlists.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    conn = get_db()
    cur = conn.cursor()
    columns = [row["name"] for row in cur.execute("PRAGMA table_info(systems)").fetchall()]

    if "list_type" not in columns:
        cur.execute("ALTER TABLE systems ADD COLUMN list_type TEXT DEFAULT 'trunked'")
        cur.execute("UPDATE systems SET list_type = 'trunked' WHERE list_type IS NULL OR list_type = ''")
        conn.commit()

    conn.close()


def normalize_list_type(raw_value):
    return "conventional" if raw_value == "conventional" else "trunked"


def get_system_folder(name):
    return os.path.join(BASE_DIR, name)


def insert_system(cur, name, list_type):
    cur.execute(
        "INSERT INTO systems (name, list_type) VALUES (?, ?)",
        (name, list_type),
    )
    return cur.lastrowid


def save_scanlist_files(folder, sites_file=None, tg_file=None):
    os.makedirs(folder, exist_ok=True)

    if sites_file:
        sites_file.save(os.path.join(folder, "sites.csv"))

    if tg_file:
        tg_file.save(os.path.join(folder, "talkgroups.csv"))


def insert_sites(cur, system_id, raw):
    reader = csv.DictReader(StringIO(raw))
    for row in reader:
        cur.execute(
            """
            INSERT INTO sites (system_id, rfss, site_dec, site_hex, nac, description, county, lat, lon, range_km)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                system_id,
                int(row["RFSS"]),
                int(row["Site Dec"]),
                row["Site Hex"],
                row["Site NAC"] or None,
                row["Description"],
                row["County Name"],
                float(row["Lat"]),
                float(row["Lon"]),
                float(row["Range"]),
            ),
        )

        site_id = cur.lastrowid
        # CSV rows may contain additional unheaded columns after "Frequencies".
        # DictReader stores those overflow values under the None key, so include them.
        freqs = [row["Frequencies"], *(row.get(None) or [])]

        for freq_value in freqs:
            if not freq_value:
                continue
            is_control = 1 if "c" in freq_value else 0
            freq = float(freq_value.replace("c", ""))
            cur.execute(
                """
                INSERT INTO frequencies (site_id, freq, is_control)
                VALUES (?, ?, ?)
                """,
                (site_id, freq, is_control),
            )


def insert_talkgroups(cur, system_id, raw):
    reader = csv.DictReader(StringIO(raw))
    for row in reader:
        decimal_str = row.get("Decimal", "").strip()
        if not decimal_str:
            continue  # skip rows with empty decimal
        try:
            decimal = int(decimal_str)
        except ValueError:
            continue  # skip invalid decimals
        cur.execute(
            """
            INSERT INTO talkgroups (system_id, decimal, hex, alpha, mode, description, tag, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                system_id,
                decimal,
                row.get("Hex", ""),
                row.get("Alpha Tag", ""),
                row.get("Mode", ""),
                row.get("Description", ""),
                row.get("Tag", ""),
                row.get("Category", ""),
            ),
        )


def replace_sites(cur, system_id, raw):
    cur.execute("DELETE FROM sites WHERE system_id = ?", (system_id,))
    insert_sites(cur, system_id, raw)


def replace_talkgroups(cur, system_id, raw):
    cur.execute("DELETE FROM talkgroups WHERE system_id = ?", (system_id,))
    insert_talkgroups(cur, system_id, raw)


def build_site_rows(cur, system_id):
    site_rows = cur.execute(
        """
        SELECT id, site_dec, site_hex, nac, description
        FROM sites
        WHERE system_id = ?
        ORDER BY site_dec
        """,
        (system_id,),
    ).fetchall()

    rows = []
    for site in site_rows:
        freqs = cur.execute(
            """
            SELECT freq, is_control
            FROM frequencies
            WHERE site_id = ?
            ORDER BY freq
            """,
            (site["id"],),
        ).fetchall()

        formatted_freqs = []
        for freq in freqs:
            suffix = "c" if freq["is_control"] else ""
            formatted_freqs.append(f'{freq["freq"]}{suffix}')

        rows.append(
            {
                "site_dec": site["site_dec"],
                "site_hex": site["site_hex"],
                "nac": site["nac"] or "",
                "description": site["description"],
                "frequencies": ", ".join(formatted_freqs),
            }
        )

    return rows


def build_talkgroup_rows(cur, system_id):
    rows = cur.execute(
        """
        SELECT decimal, hex, alpha, mode, description, tag, category
        FROM talkgroups
        WHERE system_id = ?
        ORDER BY decimal
        """,
        (system_id,),
    ).fetchall()

    return [
        {
            "decimal": row["decimal"],
            "hex": row["hex"],
            "alpha": row["alpha"],
            "mode": row["mode"],
            "description": row["description"],
            "tag": row["tag"],
            "category": row["category"],
        }
        for row in rows
    ]


def get_scanlists(cur):
    rows = cur.execute(
        """
        SELECT id, name, COALESCE(list_type, 'trunked') AS list_type
        FROM systems
        ORDER BY name COLLATE NOCASE, id
        """
    ).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "list_type": normalize_list_type(row["list_type"]),
        }
        for row in rows
    ]


def get_scanlist_detail(cur, system_id):
    row = cur.execute(
        """
        SELECT id, name, COALESCE(list_type, 'trunked') AS list_type
        FROM systems
        WHERE id = ?
        """,
        (system_id,),
    ).fetchone()

    if not row:
        return None

    folder = get_system_folder(row["name"])
    return {
        "id": row["id"],
        "name": row["name"],
        "list_type": normalize_list_type(row["list_type"]),
        "sites": build_site_rows(cur, system_id),
        "talkgroups": build_talkgroup_rows(cur, system_id),
        "sites_filename": "sites.csv" if os.path.exists(os.path.join(folder, "sites.csv")) else "",
        "talkgroups_filename": "talkgroups.csv" if os.path.exists(os.path.join(folder, "talkgroups.csv")) else "",
    }


def get_selected_scanlist(cur, requested_id):
    scanlists = get_scanlists(cur)
    if not scanlists:
        return scanlists, None

    selected_id = requested_id or scanlists[0]["id"]
    selected = get_scanlist_detail(cur, selected_id)

    if selected:
        return scanlists, selected

    fallback = get_scanlist_detail(cur, scanlists[0]["id"])
    return scanlists, fallback


def move_scanlist_folder(old_name, new_name):
    old_folder = get_system_folder(old_name)
    new_folder = get_system_folder(new_name)

    if old_folder == new_folder:
        os.makedirs(new_folder, exist_ok=True)
        return new_folder

    if os.path.exists(old_folder) and not os.path.exists(new_folder):
        shutil.move(old_folder, new_folder)
    else:
        os.makedirs(new_folder, exist_ok=True)

    return new_folder


@app.route("/")
def home():
    ensure_schema()

    requested_id = request.args.get("scanlist_id", type=int)
    new_mode = request.args.get("mode") == "new"

    conn = get_db()
    cur = conn.cursor()
    scanlists, selected_scanlist = get_selected_scanlist(cur, requested_id)
    conn.close()

    if new_mode:
        selected_scanlist = None

    return render_template(
        "index.html",
        scanlists=scanlists,
        selected_scanlist=selected_scanlist,
        is_new=new_mode or selected_scanlist is None,
    )


@app.route("/api/scanlists")
def api_scanlists():
    ensure_schema()
    conn = get_db()
    cur = conn.cursor()
    scanlists = get_scanlists(cur)
    conn.close()
    return jsonify(scanlists)


@app.route("/api/scanlists/<int:system_id>")
def api_scanlist_detail(system_id):
    ensure_schema()
    conn = get_db()
    cur = conn.cursor()
    detail = get_scanlist_detail(cur, system_id)
    conn.close()

    if not detail:
        return jsonify({"error": "scan list not found"}), 404

    return jsonify(detail)


@app.route("/upload_scanlist", methods=["POST"])
def upload_scanlist():
    ensure_schema()

    name = (request.form.get("name") or "").strip()
    list_type = normalize_list_type(request.form.get("list_type"))
    sites_file = request.files.get("sites")
    tg_file = request.files.get("talkgroups")

    if not name or not sites_file or not tg_file:
        return jsonify({"error": "missing fields"}), 400

    conn = get_db()
    cur = conn.cursor()
    system_id = insert_system(cur, name, list_type)

    folder = get_system_folder(name)
    save_scanlist_files(folder, sites_file, tg_file)

    with open(os.path.join(folder, "sites.csv"), "r", encoding="utf-8-sig") as file_obj:
        insert_sites(cur, system_id, file_obj.read())

    with open(os.path.join(folder, "talkgroups.csv"), "r", encoding="utf-8-sig") as file_obj:
        insert_talkgroups(cur, system_id, file_obj.read())

    conn.commit()
    conn.close()

    return redirect(url_for("home", scanlist_id=system_id))


@app.route("/scanlists/<int:system_id>/update", methods=["POST"])
def update_scanlist(system_id):
    ensure_schema()

    name = (request.form.get("name") or "").strip()
    list_type = normalize_list_type(request.form.get("list_type"))
    sites_file = request.files.get("sites")
    tg_file = request.files.get("talkgroups")

    if not name:
        return jsonify({"error": "missing name"}), 400

    conn = get_db()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id, name FROM systems WHERE id = ?",
        (system_id,),
    ).fetchone()

    if not existing:
        conn.close()
        return jsonify({"error": "scan list not found"}), 404

    folder = move_scanlist_folder(existing["name"], name)

    cur.execute(
        "UPDATE systems SET name = ?, list_type = ? WHERE id = ?",
        (name, list_type, system_id),
    )

    if sites_file and sites_file.filename:
        save_scanlist_files(folder, sites_file=sites_file)
        with open(os.path.join(folder, "sites.csv"), "r", encoding="utf-8-sig") as file_obj:
            replace_sites(cur, system_id, file_obj.read())

    if tg_file and tg_file.filename:
        save_scanlist_files(folder, tg_file=tg_file)
        with open(os.path.join(folder, "talkgroups.csv"), "r", encoding="utf-8-sig") as file_obj:
            replace_talkgroups(cur, system_id, file_obj.read())

    conn.commit()
    conn.close()

    return redirect(url_for("home", scanlist_id=system_id))


if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=80)
