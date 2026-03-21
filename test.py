import requests
import json

url = f"http://127.0.0.1:{8080}/"
r = requests.post(
    url,
    json = [{"command": "update", "arg1": 0, "arg2": 0}],
    timeout = 1.0
)
print(json.dumps(r.json()))

tl = r.json()['tl'].split(" ")

nac = tl[1]
wacn = tl[3]
sysid = tl[5]
tsbks = tl[8]

print(nac, wacn, sysid, tsbks)