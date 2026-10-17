# qbitpatches

Racing / seeding patches for [qbittorrent-nox-static](https://github.com/userdocs/qbittorrent-nox-static)
(`qbt_patches_url="ViktorsBaikers/qbitpatches"` or `-pr ViktorsBaikers/qbitpatches`).

Target: dedicated 10 Gbit/s Linux seedbox (NVMe RAID, 62 GB RAM), private-tracker racing via autobrr, long-term
seeding, Plex/\*arr on the same box. Every setting decision is listed in [SETTINGS.md](SETTINGS.md).

## Result (lab, 50 ms RTT, 8 peers, 20 GB torrent, 16 MiB pieces)

| | download | upload (seeding to 8 leechers) | CPU s/GB down / up |
|---|---|---|---|
| official 5.2.4 + lt 1.2.20 release, same racing config | 0.49-0.50 GB/s | 0.58 GB/s | 2.6 / 1.8 |
| this build, encryption allowed (qBittorrent's stock mode) | 0.58-0.63 GB/s | 0.80 GB/s | 2.3 / 1.5 |
| **this build, defaults (encryption disabled)** | **1.10-1.23 GB/s** | **2.09-2.27 GB/s** | 1.5 / 0.9 |

Ranges are over 2-3 runs. That is about 2.4x download and 3.6x upload over the official release. A 10 Gbit/s link is 1.25 GB/s: this build fills it in both
directions; the official release reaches 40-45 %.

## Versions

| Component | Version | Why |
|---|---|---|
| qBittorrent | **5.2.4** | latest stable |
| libtorrent | **1.2.20** (RC_1_2) | measured against 2.0.15 below |
| OpenSSL | **3.5 LTS** (3.5.9) | Boost 1.86 asio (pinned by lt 1.2) does not compile against OpenSSL 4.0 |
| toolchain | userdocs **cross** toolchain (GCC 16.2), generic x86-64, no LTO | see "Build" |

### libtorrent 1.2 vs 2.0 (same qBittorrent 5.2.4 and config, 8 peers, 50 ms RTT)

Plaintext (encryption off):

| engine | download | CPU s/GB | upload | CPU s/GB | peak RSS |
|---|---|---|---|---|---|
| **1.2.20 + this patch** | **1.10-1.23 GB/s** | **1.5-1.6** | **2.09-2.27 GB/s** | **0.9** | 4.9 GB (= 4 GiB cache) |
| 1.2.20 stock | 1.12-1.23 GB/s | 1.4-1.6 | 1.05 GB/s | 0.56 | 4.9 GB |
| 2.0.15 stock, pread disk I/O | 0.92-1.04 GB/s | 4.0-4.5 | 1.96 GB/s | 1.42 | 0.4 GB |
| 2.0.15 stock, mmap disk I/O (default) | 0.85-0.91 GB/s | 9.5-11.1 | 2.00 GB/s | 1.28 | 20 GB (whole file mapped) |

Encryption allowed (qBittorrent's stock mode, peers negotiate RC4):

| engine | download | CPU s/GB | upload | CPU s/GB |
|---|---|---|---|---|
| **1.2.20 + this patch** | **0.58-0.63 GB/s** | **2.3** | **0.80 GB/s** | **1.5** |
| 1.2.20 stock | 0.49-0.50 GB/s | 2.6 | 0.58 GB/s | 1.8 |
| 2.0.15 stock, pread | 0.50 GB/s | 5.2 | 0.60 GB/s | 2.0 |
| 2.0.15 stock, mmap | 0.46 GB/s | 11.5 | 0.59 GB/s | 2.1 |

- Download: 1.2 is 15-30 % faster than 2.0, and 2.0 needs 3-7x the CPU per byte (libtorrent runs all peer I/O on
  **one network thread**, so CPU per byte is the limit, see "Limits").
- Upload: stock 1.2 loses (1.05 vs 2.0 GB/s) only because it advertises `reqq` 500 (see below). With this patch
  (2000, same as 2.0) 1.2 is the fastest and still uses the least CPU.
- An 18-run bisect (every patched default reverted, alone and in groups) found no download difference between this
  patch and stock 1.2: all runs fall in 1.10-1.18 GB/s.

### `max_allowed_in_request_queue` is what peers pipeline to you

libtorrent sends `max_allowed_in_request_queue` to every peer as `reqq` in the extension handshake, and a libtorrent
peer **adopts it unclamped** as its per-connection request queue (`bt_peer_connection.cpp`
`max_out_request_queue(reqq)`). Consequences:
- your own `RequestQueueSize` is overridden by each seeder's `reqq` (why sweeping it changed nothing);
- stock 1.2 (500) caps every leecher at 500 x 16 KiB per RTT = 164 MB/s at 50 ms;
- a huge value is harmful: Deluge's ltConfig had 50000, so leechers queued 800 MB of requests each and seeding
  collapsed to 0.53 GB/s at 2.05 CPU s/GB. At 2000: 2.15 GB/s at 0.72 (single-setting bisect).

## Patches

The build script only reads `patches/<module>/<version>/` (`patch`, `url`, `*.patch`, `*.diff`, `source/`), and the
version folder must match exactly: `libtorrent/1.2.20`, `qbittorrent/5.2.4`. `libtorrent/v1.2.20/`, `RC_1_2/` and
`patch.eof` files are never picked up and are kept only for history.

### `patches/libtorrent/1.2.20/patch`

1. **MSE/PE handshake: OpenSSL bignum + 160-bit exponent.** Backport of upstream
   [#8565](https://github.com/arvidn/libtorrent/pull/8565) (160-bit DH secret, merged in RC_2_0) and
   [#8660](https://github.com/arvidn/libtorrent/pull/8660) (libcrypto `BN_mod_exp`, merged in RC_2_1). Includes the
   2.0 fixes: reject degenerate remote keys (`< 2` or `>= p-1`) and fixed-width key export (1.2.20 drops roughly 1 in
   256 encrypted handshakes when the shared secret has a leading zero byte).
   One handshake goes from 886 us to 46 us of network-thread time. A 500-peer race start goes from 443 ms to 23 ms.
2. **RC4 via OpenSSL.** libtorrent's byte loop does 0.83 GB/s/core and OpenSSL's `RC4()` does 1.32 GB/s/core. The
   keystream is identical (verified), so the change is wire-compatible. It only matters when a connection is encrypted.
3. **Defaults qBittorrent never sets** (anything qBittorrent sets would be overwritten):

| setting | stock | new | reason |
|---|---|---|---|
| `torrent_connect_boost` | 30 | 200 | connect to the whole first announce immediately |
| `smooth_connects` | true | false | allow connection bursts at race start |
| `strict_end_game_mode` | true | false | request the last blocks from several peers |
| `max_allowed_in_request_queue` | 500 | 2000 | fast leechers may pipeline 32 MiB (HPS, lt 2.0 default) |
| `request_queue_time` | 3 | 5 | deeper pipeline to fast high-RTT peers |
| `request_timeout` / `piece_timeout` | 60 / 20 | 20 / 10 | re-request stalled blocks sooner |
| `min_reconnect_time` | 60 | 10 | retry dropped peers sooner |
| `max_failcount` | 3 | 5 | racing swarms are flaky |
| `peer_connect_timeout` | 15 | 10 | free half-open slots faster |
| `allowed_fast_set_size` | 5 | 0 | everyone is unchoked anyway (HPS) |
| `max_rejects` | 50 | 10 | HPS |
| `max_peer_recv_buffer_size` | 2 MiB | 5 MiB | HPS |
| `write_cache_line_size` | 16 | 256 | flush 4 MiB at a time (HPS; matches RAID stripes) |
| `tick_interval` | 500 ms | 250 ms | faster rate / request-queue adaptation |
| `predictive_piece_announce` | 0 | 20 ms | HAVE just before a piece completes |
| `send_not_sent_low_watermark` | 16 KiB | 512 KiB | per-socket TCP_NOTSENT_LOWAT (HPS) |

(HPS = libtorrent's own `high_performance_seed()` preset. Every HPS value is now applied by qBittorrent or this
patch, or deliberately kept. `peer_timeout`/`inactivity_timeout` stay at 120/600 s, because 20 s would drop peers
that send legal 120 s keep-alives.)

### `patches/qbittorrent/5.2.4/patch`

1. **Racing defaults** for a fresh profile (an existing `qBittorrent.conf` value still wins): no queueing, unlimited
   active torrents / upload slots / connections per torrent, 20000 connections, 500 connections/s, request queue 1500,
   disk queue 64 MiB, disk cache 4 GiB, 16 async I/O threads, file pool 5000, send buffer 20 MiB / 3 MiB / 200 %,
   backlog 3000, 200 concurrent announces, suggest mode, piece extent affinity, multiple connections per IP, TCP only,
   LSD off, preallocation, **encryption disabled**. `upgrade.cpp`: the legacy fallback for `QueueingSystemEnabled`
   in upgraded profiles is `false` as well.
2. **Bug fix**: `SendBufferWatermark` / `SendBufferLowWatermark` (KiB x 1024 in a 32-bit `int`) wrapped for large
   values. They are now clamped to `INT_MAX`.

## Encryption

qBittorrent hardcodes `allowed_enc_level=pe_rc4` + `prefer_rc4`: with the stock "allow encryption" mode every
connection to another qBittorrent/Deluge peer runs RC4 on every byte, on the single network thread. Measured:

| 8 peers | encryption allowed (stock) | disabled |
|---|---|---|
| upload | 0.80 GB/s (2 runs: 0.80, 0.80) | 2.09-2.27 GB/s |
| download | 0.58-0.63 GB/s | 1.14-1.23 GB/s |

Disabled = plaintext only. Peers that *allow* encryption (the default everywhere) retry plaintext automatically. The
lab peers ran with encryption allowed, so the numbers above include that fallback. Only peers set to *require*
encryption can no longer connect. On private trackers these are rare, and they are almost always throttled home
connections. Set `Session\Encryption=0` to go back.

## Deluge (linuxserver/deluge:libtorrentv1 - Deluge 2.2.0, libtorrent 1.2.20, Docker bridge network)

`deluge/apply_tuning.py <config dir>` edits `core.conf` + `ltconfig.conf` (run it while deluged is stopped). The
lab ran the exact production image and config in Docker (`tools/dlab.py`), against the same 8 peers:

| Deluge config | download | upload | CPU s/GB down / up |
|---|---|---|---|
| before (production) | 0.43-0.45 GB/s | **0** - torrent paused on completion | 2.9 / - |
| before, ratio fix only | 0.43-0.45 GB/s | 0.37 GB/s | 2.9 / 2.9 |
| + encryption off | 0.93-0.94 GB/s | 0.53 GB/s | 1.8 / 2.1 |
| **+ ltConfig fixes (= apply_tuning.py)** | **0.91-0.98 GB/s** | **2.02-2.18 GB/s** | 1.8 / 0.75 |
| same + `network_mode: host` | 0.93-0.96 GB/s | 2.26-2.33 GB/s | 1.7 / 0.75 |
| qBittorrent (this build), same setup | 1.11 GB/s | 2.09-2.13 GB/s | 1.6 / 0.9 |

What was wrong:
- `stop_seed_at_ratio: true` + `stop_seed_ratio: 0.0` - Deluge's `TorrentManager.update()` pauses every finished
  torrent whose ratio >= 0.0, i.e. immediately. New torrents never seeded.
- `max_allowed_in_request_queue: 50000` - see above, 4x seeding loss.
- encryption allowed with RC4 - 2x download cost.
- smaller items set back to sane values: `max_out_request_queue` 50000, `tick_interval` 100 ms, request/piece
  timeouts 8/5 s, `peer_timeout`/`inactivity_timeout` 45/60 s (drops idle-but-legal peers on long-term seeds),
  `min_reconnect_time` 0, `max_failcount` 100, parole mode off, incoming uTP on, outgoing ports bound to
  60000-64999 in `core.conf`, and 5 settings libtorrent 1.2 no longer has.

Not changed: host networking is ~5 % faster on upload but changes how Traefik reaches the WebUI. Rebuilding the
image's libtorrent (GCC 15 / clang 21, with this repo's patch) gained only 2-4 % (0.91 -> 0.93/0.95), not worth a
custom image. The remaining ~15 % gap to qBittorrent sits on libtorrent's network thread (97 % busy, Python threads
< 10 %); the effective libtorrent settings are otherwise the same. Torrents already in Deluge keep the per-torrent
`stop_at_ratio` they were added with.

## Lab

`tools/lab.py`: a network namespace with veth + netem (50 ms RTT), a 20 GB random-data private torrent with 16 MiB
pieces, and 4 or 8 fixed peers (official 1.2.20 release). Every candidate gets an identical qBittorrent config, the
page cache is dropped before each run, and the script records wall time, candidate CPU seconds and peak RSS.

Swept with no effect beyond run-to-run noise (+-5 %), so the values stay (details in SETTINGS.md):
`RequestQueueSize` 500/2000/3000, send buffer 5/1/100 and 64/8/300, `AsyncIOThreadsCount` 8/32,
`DiskCacheSize` 1/8 GiB, `DiskCacheTTL` 30, `DiskIOReadMode`/`WriteMode` O_DIRECT, `SuggestMode` off.

## Limits

During a plaintext download one thread of qBittorrent sits at 95 % CPU while every other thread stays under 10 %.
That thread is libtorrent's network thread, which handles all peers: about 1.2 GB/s download and 2.2 GB/s upload per
client on a modern x86 core. Maintainer arvidn describes this limit in
[libtorrent #7399](https://github.com/arvidn/libtorrent/issues/7399). No setting raises it; only less work per byte
does (the DH/RC4 changes above, encryption off, no uTP). To go beyond one 10 Gbit/s link, run more than one client
instance.

## Build

```bash
docker run --rm -v "$PWD":/work -w /work \
  -e qbt_build_dir=build -e qbt_cross_name=x86_64 \
  -e qbt_libtorrent_version=1.2 -e qbt_libtorrent_tag=v1.2.20 \
  -e qbt_qbittorrent_tag=release-5.2.4 -e qbt_openssl_tag=openssl-3.5.9 \
  -e qbt_build_tool=cmake -e qbt_qt_version=6 -e qbt_optimise=no \
  -e qbt_patches_url=ViktorsBaikers/qbitpatches \
  alpine:edge sh -c 'apk add bash curl git && curl -sL https://raw.githubusercontent.com/userdocs/qbittorrent-nox-static/master/qbt-nox-static.bash -o qbt.bash \
    && bash qbt.bash install_core && bash qbt.bash all'
# -> build/completed/qbittorrent-nox (static, runs on any x86-64 Linux)
```

- `qbt_cross_name=x86_64` builds with the same musl cross toolchain as the official releases. The `qbt_build_dir`
  path must be **relative**: an absolute path breaks in cross mode (`/work//work/...`).
- Native Alpine GCC 15 with LTO, `-fcf-protection=full` and `-march=znver4` measured **~15 % more CPU per byte**
  (download 0.42-0.45 GB/s against 0.52 GB/s for the release build). The bisect pointed at the toolchain, not the
  patches. `znver4` against generic x86-64 made no difference, so the build stays generic.
- The script unsets `qbt_cflags`/`qbt_cxxflags`/`qbt_ldflags`. Custom flags go in `CFLAGS`/`CXXFLAGS`/`LDFLAGS`,
  but none are needed.

`tools/` holds the lab scripts (`lab.py` qBittorrent, `dlab.py` Deluge in Docker), the DH and RC4 micro-benchmarks,
the per-thread CPU profiler, and `qbittorrent-lab-env-overrides.patch` (lab only: lets a test build take any libtorrent
setting from `QBT_LT_OVERRIDES`; never used for release builds).
