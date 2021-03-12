#!/bin/ash

# Create conf directory if it doesn't exist 
mkdir -p /data/zigsniff

#!/bin/bash

d=$(date +%Y%m%d-%H%M%S)

cd /data/zigsniff

[[ -f surepet.db ]] && echo "Surepet.db exists" || sqlite3 surepet.db < /data/surepet.sql

exec /data/whsniff -c 15 | tee $d.pcap | tshark -r - -T fields -e frame.time -e wpan.src64 -e wpan.dst64 -e data -l | unbuffer -p tee $d.txt | grep --line-buffered -P "\t01" | python3 -u /data/parsezig.py | unbuffer -p tee $d.update.txt
