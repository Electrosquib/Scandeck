from flask import Flask, render_template, request, jsonify
import csv
from io import StringIO
import os
import sqlite3

app = Flask(__name__)

BASE_DIR = "/home/scandeck-one/Scandeck/Scan Lists"
DB_PATH = "scanlists.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_system(cur, name):
    cur.execute("INSERT INTO systems (name) VALUES (?)", (name,))
    return cur.lastrowid


def insert_sites(cur, system_id, raw):
    reader = csv.DictReader(StringIO(raw))
    for row in reader:
        cur.execute("""
        INSERT INTO sites (system_id, rfss, site_dec, site_hex, nac, description, county, lat, lon, range_km)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            system_id,
            int(row["RFSS"]),
            int(row["Site Dec"]),
            row["Site Hex"],
            row["Site NAC"] or None,
            row["Description"],
            row["County Name"],
            float(row["Lat"]),
            float(row["Lon"]),
            float(row["Range"])
        ))

        site_id = cur.lastrowid

        freqs = row["Frequencies"].split(",")

        for f in freqs:
            is_control = 1 if "c" in f else 0
            freq = float(f.replace("c", ""))

            cur.execute("""
            INSERT INTO frequencies (site_id, freq, is_control)
            VALUES (?, ?, ?)
            """, (site_id, freq, is_control))


def insert_talkgroups(cur, system_id, raw):
    reader = csv.DictReader(StringIO(raw))
    for row in reader:
        cur.execute("""
        INSERT INTO talkgroups (system_id, decimal, hex, alpha, mode, description, tag, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            system_id,
            int(row["Decimal"]),
            row["Hex"],
            row["Alpha Tag"],
            row["Mode"],
            row["Description"],
            row["Tag"],
            row["Category"]
        ))


@app.route("/")
def home():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM sites")
    sites = cur.fetchall()

    cur.execute("SELECT * FROM talkgroups")
    tgs = cur.fetchall()

    conn.close()

    return render_template("index.html", data={"sites": sites, "talkgroups": tgs})


@app.route("/upload_scanlist", methods=["POST"])
def upload_scanlist():
    name = request.form.get("name")
    sites_file = request.files.get("sites")
    tg_file = request.files.get("talkgroups")

    if not name or not sites_file or not tg_file:
        return jsonify({"error": "missing fields"}), 400

    folder = os.path.join(BASE_DIR, name)
    os.makedirs(folder, exist_ok=True)

    sites_path = os.path.join(folder, "sites.csv")
    tg_path = os.path.join(folder, "talkgroups.csv")

    sites_file.save(sites_path)
    tg_file.save(tg_path)

    # --- NEW: insert into DB ---
    conn = get_db()
    cur = conn.cursor()

    system_id = insert_system(cur, name)

    with open(sites_path, "r") as f:
        insert_sites(cur, system_id, f.read())

    with open(tg_path, "r") as f:
        insert_talkgroups(cur, system_id, f.read())

    conn.commit()
    conn.close()
    # --------------------------

    return jsonify({
        "status": "ok",
        "system_id": system_id
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)