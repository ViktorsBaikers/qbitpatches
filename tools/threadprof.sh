#!/bin/bash
# threadprof.sh <seconds> - per-thread CPU % of the lab candidate (cand0) over a window, busiest first
pid=$(for p in $(pgrep -f "cand0/profil[e]"); do ! grep -qx runuser /proc/$p/comm && echo $p; done | head -1)
[ -z "$pid" ] && { echo "no candidate"; exit 1; }
snap() { for t in /proc/$pid/task/*; do echo "$(basename $t) $(cat $t/comm | tr ' ' _) $(awk '{print $14+$15}' $t/stat)"; done; }
a=$(snap); sleep "$1"; b=$(snap)
join <(echo "$a" | sort) <(echo "$b" | sort) | awk -v s="$1" '{printf "%6.1f%% %s\n", ($5-$3)/s, $2}' | sort -rn | head -12
