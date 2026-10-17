# qbitpatches

Racing / seeding tuned patches for [qbittorrent-nox-static](https://github.com/userdocs/qbittorrent-nox-static)
(`qbt_patches_url="ViktorsBaikers/qbitpatches"` or `-pr ViktorsBaikers/qbitpatches`).

Target: dedicated 10 Gbit/s Linux seedbox (Zen 4, NVMe RAID, 62 GB RAM), private-tracker racing via autobrr,
long-term seeding, Plex/*arr on the same box.

## Versions (2026-10)

| Component | Version | Why |
|---|---|---|
| qBittorrent | **5.2.4** | latest stable (5.3.0 is still rc) |
| libtorrent | **1.2.20** (RC_1_2) | keeps the application-level disk cache (write coalescing, hash-from-memory, read cache with piece suggestions). 2.0 drops it for mmap (kernel cache only); 2.1's new pread backend still gets write-path fixes in the unreleased 2.1.3. nox-static ships 5.2.4 + 1.2.20 builds. |
| OpenSSL | **3.5 LTS** (3.5.9) | libtorrent 1.2 pins Boost 1.86, whose asio SSL code does not compile against OpenSSL 4.0 (opaque `ASN1_STRING`). |

## Active patches

The build script only looks at `patches/<module>/<version>/` and only reads `patch`, `url`, `Jamfile`,
`*.patch`, `*.diff` (and a `source/` overlay). **Version folder names must match exactly what the script
computes**: `libtorrent/1.2.20`, `qbittorrent/5.2.4`.

> The older folders `libtorrent/v1.2.20/` and `libtorrent/RC_1_2/` are **never picked up** by the current
> script (it looks for `1.2.20`), and `patch.eof` files are ignored. They are kept only for history.

### `patches/libtorrent/1.2.20/patch`

qBittorrent 5.2.4 overwrites every libtorrent setting it exposes, so changing those defaults in libtorrent
has no effect. This patch only changes settings **qBittorrent never sets** - otherwise unreachable without
code. Values follow libtorrent's own `high_performance_seed()` preset, adjusted for racing downloads.

| setting | stock | new | reason |
|---|---|---|---|
| `torrent_connect_boost` | 30 | 200 | connect to the whole first announce (num_want=200) immediately |
| `smooth_connects` | true | false | allow connection bursts at race start |
| `strict_end_game_mode` | true | false | request the last blocks from several peers |
| `max_allowed_in_request_queue` | 500 | 2000 | fast leechers may pipeline 32 MiB (HPS) |
| `request_queue_time` | 3 | 5 | deeper pipeline to fast high-RTT peers |
| `request_timeout` / `piece_timeout` | 60 / 20 | 20 / 10 | re-request stalled blocks sooner |
| `min_reconnect_time` | 60 | 10 | retry dropped peers sooner |
| `max_failcount` | 3 | 5 | racing swarms are flaky (HPS uses 1 - seed only) |
| `peer_connect_timeout` | 15 | 10 | free half-open slots faster |
| `allowed_fast_set_size` | 5 | 0 | everyone is unchoked anyway (HPS) |
| `max_rejects` | 50 | 10 | HPS |
| `max_peer_recv_buffer_size` | 2 MiB | 5 MiB | HPS |
| `write_cache_line_size` | 16 | 256 | flush 4 MiB at a time (HPS; matches 512K/1M RAID stripes) |
| `tick_interval` | 500 ms | 250 ms | faster rate / request-queue adaptation |
| `predictive_piece_announce` | 0 | 20 ms | send HAVE just before a piece completes (only when all remaining blocks come from one peer) |
| `send_not_sent_low_watermark` | 16 KiB | 512 KiB | per-socket TCP_NOTSENT_LOWAT (HPS) |

Deliberately **unchanged**: `peer_timeout` 120 / `inactivity_timeout` 600 (peers may legally keep-alive every
120 s), `use_parole_mode`, `close_redundant_connections`, `num_want`.

### `patches/qbittorrent/5.2.4/patch`

1. **Racing defaults** for settings qBittorrent owns (a fresh profile is tuned; existing configs still win):
   unlimited upload slots (global + per torrent; stock 20 / **4**), unlimited connections per torrent,
   20000 global, connection speed 500/s (stock 30), request queue 1500, disk queue 64 MiB (stock 1 MiB),
   disk cache 4096 MiB (auto would be ~1.6 GiB on 62 GB), async I/O threads 16 (= 4 hasher threads, stock 2),
   file pool 5000, checking memory 1024 MiB, send buffer 20 MiB / low 3 MiB / factor 200 %, listen backlog 3000,
   200 concurrent HTTP announces, suggest mode, piece extent affinity, multiple connections per IP,
   TCP-only (no uTP), LSD off, **preallocation on** (measured on XFS/NVMe: +10 % buffered and +48 % direct
   random-write throughput vs sparse files), **queueing off** with unlimited active limits.
   `src/app/upgrade.cpp`: qBittorrent writes `QueueingSystemEnabled=true` into *existing* profiles that lack
   the key ("legacy" defaults, 3 downloads / 3 uploads / 5 active). For racing a new torrent must never sit
   queued, so the legacy fallback is `false` too.
2. **Bug fix**: `SendBufferWatermark` / `SendBufferLowWatermark` are KiB values multiplied by 1024 into a
   32-bit `int`; large values wrapped (e.g. 8388608 KiB -> 0). Now clamped to `INT_MAX`.

Not changed on purpose (security/stability): CSRF protection, alert queue size, active tracker/DHT limits.

## Measured (2026-10-17, 10G Amsterdam box, Ubuntu 26.04.1 ISO swarm, 6.48 GB, median of 3)

| | stock 5.2.4/1.2.20 release + same racing config | this build (patched defaults) |
|---|---|---|
| complete, from add | 15.06 s | 15.33 s |
| first GB | 5.54 s | 5.53 s |
| peak 1 s | 1267 MB/s | 1174 MB/s |

Both saturate the 10 Gbit/s link: in a large public swarm a download is link-bound. The libtorrent-internal
defaults target racing upload, small swarms and end-game, which a public swarm can't exercise; they showed no
cost. The main gains over 4.3.9 come from qBittorrent 5.2.4 exposing connection speed / request queue /
disk queue and from correct settings - which this build makes the defaults.

## Build

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e qbt_build_dir=/work/build \
  -e qbt_libtorrent_version=1.2 -e qbt_libtorrent_tag=v1.2.20 \
  -e qbt_qbittorrent_tag=release-5.2.4 -e qbt_openssl_tag=openssl-3.5.9 \
  -e qbt_build_tool=cmake -e qbt_qt_version=6 -e qbt_use_lto=yes \
  -e qbt_patches_url=ViktorsBaikers/qbitpatches \
  -e CFLAGS="-march=znver4 -mtune=znver4" -e CXXFLAGS="-march=znver4 -mtune=znver4" \
  -e LDFLAGS="-march=znver4 -mtune=znver4" \
  alpine:edge sh -c 'apk add bash curl git && curl -sL https://raw.githubusercontent.com/userdocs/qbittorrent-nox-static/master/qbt-nox-static.bash -o qbt.bash \
    && bash qbt.bash install_core && bash qbt.bash all'
# -> build/completed/qbittorrent-nox
```

Notes: the script **unsets** `qbt_cflags`/`qbt_cxxflags`/`qbt_ldflags` and reads the standard
`CFLAGS`/`CXXFLAGS`/`LDFLAGS` instead. `-march=znver4` targets Zen 4 (EPYC 4004/9004, Ryzen 7000); use
`x86-64-v3` or drop it for other CPUs. Release builds use `-O3`, LTO, and the script's hardening flags.
