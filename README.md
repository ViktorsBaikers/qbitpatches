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
| **this build, defaults (encryption disabled)** | **1.14-1.23 GB/s** | **2.09-2.27 GB/s** | 1.5 / 0.9 |

Ranges are over 2-3 runs. That is about 2.4x download and 3.6x upload over the official release. A 10 Gbit/s link is 1.25 GB/s: this build fills it in both
directions; the official release reaches 40-45 %.

## Versions

| Component | Version | Why |
|---|---|---|
| qBittorrent | **5.2.4** | latest stable |
| libtorrent | **1.2.20** (RC_1_2) | measured against 2.0.15 below |
| OpenSSL | **3.5 LTS** (3.5.9) | Boost 1.86 asio (pinned by lt 1.2) does not compile against OpenSSL 4.0 |
| toolchain | userdocs **cross** toolchain (GCC 16.2), generic x86-64, no LTO | see "Build" |

### libtorrent 1.2 vs 2.0 (same qBittorrent 5.2.4, encryption off, 4 peers)

| | download | CPU s/GB | upload | CPU s/GB | peak RSS |
|---|---|---|---|---|---|
| **1.2.20 + this patch** | 1.06 GB/s | **1.56** | 1.84 GB/s | **0.78** | 4.7 GB (= 4 GiB cache) |
| 2.0.15, pread disk I/O | 1.06 GB/s | 4.03 | 1.84 GB/s | 1.40 | 0.2 GB |
| 2.0.15, mmap disk I/O (default) | 0.96 GB/s | 9.89 | 1.89 GB/s | 1.22 | 20.5 GB (whole file mapped) |

Same throughput, but 2.0 burns 1.8-6x the CPU per byte. libtorrent runs all peer I/O on **one network thread**,
so CPU per byte is what caps a single client (see "Limits"). 1.2 stays.

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

`tools/` holds the lab script, the DH and RC4 micro-benchmarks, and the per-thread CPU profiler used for the numbers
above.
