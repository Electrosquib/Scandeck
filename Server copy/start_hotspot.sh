#!/bin/bash

nmcli connection up Hotspot

sleep 2

cd /home/scandeck-one/Scandeck
sudo /home/scandeck-one/Scandeck/.venv/bin/python Server/app.py