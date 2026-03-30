from flask import Flask, render_template, request, jsonify
import csv
from io import StringIO
import os

app = Flask(__name__)

BASE_DIR = "/home/scandeck-one/Scandeck/Scan Lists"

def parse_sites(raw: str):
    sites = []
    reader = csv.reader(StringIO(raw))
    next(reader)
    for row in reader:
        site_dec = row[1]
        site_hex = int(row[2], 16)
        nac = row[3] or ""
        desc = row[4]
        freqs = ",".join(row[9:])
        sites.append([site_dec, site_hex, nac, desc, freqs])
    return sites

def parse_tg(raw):
    reader = csv.reader(StringIO(raw))
    next(reader)
    tg = []
    for row in reader:
        tg.append([
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6]
        ])
    return tg

@app.route("/")
def home():
    with open(f"{BASE_DIR}/Honolulu_sites.csv", "r") as f:
        sites = parse_sites(f.read())
    with open(f"{BASE_DIR}/Honolulu_talkgroups.csv", "r") as f:
        tgs = parse_tg(f.read())
    return render_template("index.html", data = {"sites": sites, "talkgroups": tgs})

@app.route("/upload_scanlist", methods=["POST"])
def upload_scanlist():
    name = request.form.get("name")
    sites_file = request.files.get("sites")
    tg_file = request.files.get("talkgroups")

    if not name or not sites_file or not tg_file:
        return jsonify({"error": "missing fields"}), 400

    folder = os.path.join(BASE_DIR, name)
    os.makedirs(folder, exist_ok = True)

    sites_path = os.path.join(folder, "sites.csv")
    tg_path = os.path.join(folder, "talkgroups.csv")

    sites_file.save(sites_path)
    tg_file.save(tg_path)

    return jsonify({
        "status": "ok",
        "name": name,
        "paths": {
            "sites": sites_path,
            "talkgroups": tg_path
        }
    })

if __name__ == "__main__":
    app.run(host = "0.0.0.0", port = 80)