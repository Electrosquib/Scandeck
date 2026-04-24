import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
TRUNK_FILE = os.path.join(BASE_DIR, "trunk.tsv")
ADSB_FEED_FILE = os.path.join(BASE_DIR, "adsb.json")
ADSB_START_CMD = None
ADSB_START_CWD = BASE_DIR
