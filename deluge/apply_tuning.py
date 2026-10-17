#!/usr/bin/env python3
"""apply_tuning.py <config dir> - racing/seeding tuning for Deluge 2.2 + libtorrent 1.2 (core.conf + ltconfig.conf).

Run only while deluged is stopped (it rewrites both files on exit). Lab results: README of ViktorsBaikers/qbitpatches.
"""
import json, sys

CORE = {
    "stop_seed_at_ratio": False,     # with stop_seed_ratio 0.0 every finished torrent was paused -> no seeding at all
    "random_outgoing_ports": True,   # don't bind outgoing connections to 60000-64999
    "enc_in_policy": 2, "enc_out_policy": 2,   # encryption off (RC4 on every byte: 2x download, 4x upload cost)
}
# max_allowed_in_request_queue is advertised to peers as "reqq" and libtorrent leechers adopt it unclamped:
# 50000 let every leecher queue 800 MB of requests on us -> seeding 0.53 GB/s at 2.05 CPU-s/GB; 2000 -> 2.15 GB/s
LT = {
    "in_enc_policy": 2, "out_enc_policy": 2,
    "max_out_request_queue": 1500, "max_allowed_in_request_queue": 2000, "tick_interval": 250,
    "send_not_sent_low_watermark": 524288, "predictive_piece_announce": 20,
    "piece_timeout": 10, "request_timeout": 20, "peer_timeout": 120, "inactivity_timeout": 600,
    "min_reconnect_time": 10, "max_failcount": 5, "use_parole_mode": True, "handshake_timeout": 10,
    "peer_connect_timeout": 10, "whole_pieces_threshold": 20, "initial_picker_threshold": 4, "aio_threads": 16,
    "write_cache_line_size": 256, "enable_incoming_utp": False, "file_pool_size": 5000,
    "piece_extent_affinity": True,
}
DEPRECATED = ["cache_buffer_chunk_size", "guided_read_cache", "half_open_limit", "low_prio_disk", "rate_limit_utp"]


def load(path):
    s = open(path).read(); i = s.index("}") + 1
    return s[:i], json.loads(s[i:])


def save(path, header, body):
    open(path, "w").write(header + json.dumps(body, indent=4, sort_keys=True, ensure_ascii=False))


d = sys.argv[1]
h, core = load(f"{d}/core.conf")
for k, v in CORE.items():
    print(f"core.conf  {k}: {core.get(k)!r} -> {v!r}"); core[k] = v
save(f"{d}/core.conf", h, core)
h, ltc = load(f"{d}/ltconfig.conf")
s = ltc["settings"]
for k, v in LT.items():
    if s.get(k) != v: print(f"ltconfig   {k}: {s.get(k)!r} -> {v!r}")
    s[k] = v
for k in DEPRECATED:
    if k in s: print(f"ltconfig   {k}: removed (not a libtorrent 1.2 setting)"); del s[k]
save(f"{d}/ltconfig.conf", h, ltc)
