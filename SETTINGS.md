# Settings review - every libtorrent 1.2.20 and qBittorrent 5.2.4 setting

Each setting was checked against its documentation/source and, where it can matter for racing, measured in the lab
(see README "Lab"). Deprecated libtorrent settings (27) are omitted.

## qBittorrent 5.2.4

| qBittorrent key (`BitTorrent/Session/…`) | stock 5.2.4 | this build | why |
|---|---|---|---|
| `QueueingSystemEnabled` | false (new profile), true (upgraded profile, upgrade.cpp) | **false** | a racing torrent must never sit queued |
| `MaxActiveDownloads` / `Uploads` / `Torrents` | 3 / 3 / 5 | **-1** | same |
| `MaxConnections` | 500 | **20000** | hundreds of torrents x dozens of peers |
| `MaxConnectionsPerTorrent` | 100 | **-1** | connect to the whole swarm |
| `MaxUploads` / `MaxUploadsPerTorrent` | 20 / 4 | **-1** | unchoke every interested leecher immediately |
| `ConnectionSpeed` | 30 /s | **500 /s** | whole first announce dialled within a second |
| `SocketBacklogSize` | 30 | **3000** | burst of incoming leechers at race start |
| `MaxConcurrentHTTPAnnounces` | 50 | **200** | many torrents announcing at once |
| `RequestQueueSize` | 500 | **1500** | per-peer ceiling = queue x 16 KiB / RTT (500 -> 164 MB/s at 50 ms, 1500 -> 490 MB/s); lab (8 peers, 2 runs): 2000/3000 within noise |
| `SendBufferWatermark` / `Low` / `Factor` | 500 KiB / 10 KiB / 50 % | **20 MiB / 3 MiB / 200 %** | keeps fast high-RTT leechers fed; lab: 64/8/300 and 5/1/100 equal -> kept |
| `DiskQueueSize` | 1 MiB | **64 MiB** | stock throttles peers when only 1 MiB of writes is pending |
| `DiskCacheSize` | auto (~1.6 GiB here) | **4096 MiB** | write coalescing + read cache for seeding; lab: 1 GiB/8 GiB same speed |
| `DiskCacheTTL` | 60 s | 60 s | lab: 30 s no difference |
| `AsyncIOThreadsCount` | 10 | **16** | lt 1.2 uses 1/4 of them for hashing -> 4 hash threads; lab: 8/32 no difference |
| `HashingThreadsCount` | 1 | 1 | libtorrent 2.x only |
| `FilePoolSize` | 100 | **5000** | no fd churn with hundreds of seeding torrents |
| `CheckingMemUsageSize` | 32 MiB | **1024 MiB** | fast rechecks |
| `DiskIOReadMode` / `DiskIOWriteMode` | OS cache | OS cache | lab: O_DIRECT no measurable gain; page cache also serves Plex/\*arr and re-seeding a race |
| `CoalesceReadWrite` | false (Linux) | false | HPS also false |
| `PieceExtentAffinity` | false | **true** | 4 MiB extents -> sequential writes on RAID |
| `SuggestMode` | false | **true** | leechers prefer pieces already in our read cache |
| `Preallocation` | false | **true** | XFS/NVMe: +10 % buffered, +48 % direct random-write vs sparse |
| `MultiConnectionsPerIp` | false | **true** | seedbox neighbours share IPs |
| `BTProtocol` | TCP+uTP | **TCP** | uTP is CPU-heavy and backs off; useless on 10G |
| `LSDEnabled` | true | **false** | no LAN peers |
| `DHTEnabled` / `PeXEnabled` | true | true | ignored by private torrents; useful for public ones |
| `Encryption` | 0 (allow, RC4 preferred) | **2 (disabled)** | RC4 costs 2.7x upload / 2x download throughput (lab, 8 peers); see README "Encryption" |
| `SocketSendBufferSize` / `ReceiveBufferSize` | 0 | 0 | 0 = kernel autotuning (sysctl tcp_rmem/wmem tuned) |
| `ChokingAlgorithm` / `SeedChokingAlgorithm` | fixed slots / fastest upload | same | with unlimited slots every interested peer is unchoked |
| `PeerTurnover*` | 4 % / 90 % / 300 s | same | only acts near the connection limit |
| `AnnounceToAllTrackers` / `AllTiers` | false / true | same | private torrents have one tracker |
| `StopTrackerTimeout` | 2 s | same | |
| `ResumeDataStorageType` | Legacy | same | not on the racing path |
| `GlobalDL/UPSpeedLimit`, `IncludeOverheadInLimits`, `IgnoreLimitsOnLAN` | unlimited | same | |
| `AnonymousModeEnabled` | false | false | private trackers need the real client id |
| `ValidateHTTPSTrackerCertificate`, `SSRFMitigation`, `BlockPeersOnPrivilegedPorts` | stock | stock | security |
| proxy, I2P, IP filter, paths, categories, tags, AutoTMM, share limits, export dirs, excluded names | - | - | not performance related |

Hardcoded by qBittorrent (not configurable): `allowed_enc_level=pe_rc4`, `prefer_rc4=true`, `alert_queue_size=INT_MAX/2`,
active limits -1 when queueing is off, `listen_system_port_fallback=false`, UPnP/NAT-PMP per setting - all fine except the
RC4-only encryption level, which is why `Encryption=2` matters.

## libtorrent 1.2.20

`set by qBittorrent` = qBittorrent writes this setting on every start, so a libtorrent default is irrelevant and the
value comes from the qBittorrent table above. `patched` = changed by `patches/libtorrent/1.2.20/patch`.

| setting | default | decision | why |
|---|---|---|---|
| `user_agent` | "libtorrent/" LIBTORRENT_VERSION | set by qBittorrent | see the qBittorrent table |
| `announce_ip` | nullptr | set by qBittorrent | see the qBittorrent table |
| `handshake_client_version` | nullptr | keep | cosmetic |
| `outgoing_interfaces` | "" | set by qBittorrent | see the qBittorrent table |
| `listen_interfaces` | "0.0.0.0:6881,[::]:6881" | set by qBittorrent | see the qBittorrent table |
| `proxy_hostname` | "" | set by qBittorrent | see the qBittorrent table |
| `proxy_username` | "" | set by qBittorrent | see the qBittorrent table |
| `proxy_password` | "" | set by qBittorrent | see the qBittorrent table |
| `i2p_hostname` | "" | set by qBittorrent | see the qBittorrent table |
| `peer_fingerprint` | "-LT12K0-" | set by qBittorrent | see the qBittorrent table |
| `dht_bootstrap_nodes` | "dht.libtorrent.org:25401" | set by qBittorrent | see the qBittorrent table |
| `allow_multiple_connections_per_ip` | false | set by qBittorrent | see the qBittorrent table |
| `send_redundant_have` | true | keep | keeps peers' availability view correct; negligible cost |
| `use_dht_as_fallback` | false | set by qBittorrent | see the qBittorrent table |
| `upnp_ignore_nonrouters` | false | keep | UPnP off |
| `use_parole_mode` | true | keep | isolates peers that sent bad data - protects the race against poisoned pieces |
| `use_read_cache` | true | keep | required for suggest_mode=read cache and fast seeding |
| `coalesce_reads` | false | set by qBittorrent | see the qBittorrent table |
| `coalesce_writes` | false | set by qBittorrent | see the qBittorrent table |
| `auto_manage_prefer_seeds` | false | keep | queueing off |
| `dont_count_slow_torrents` | true | set by qBittorrent | see the qBittorrent table |
| `close_redundant_connections` | true | keep | drops seed<->seed connections once complete; frees slots (HPS keeps it on) |
| `prioritize_partial_pieces` | false | keep | false keeps rarest-first + whole-piece picking, which is what wins races |
| `rate_limit_ip_overhead` | true | set by qBittorrent | see the qBittorrent table |
| `announce_to_all_trackers` | false | set by qBittorrent | see the qBittorrent table |
| `announce_to_all_tiers` | false | set by qBittorrent | see the qBittorrent table |
| `prefer_udp_trackers` | true | keep | harmless; private trackers are HTTP(S) |
| `disable_hash_checks` | false | keep | must stay false (data integrity) |
| `allow_i2p_mixed` | false | set by qBittorrent | see the qBittorrent table |
| `volatile_read_cache` | false | keep | false: cached seed blocks stay for the next leecher |
| `no_atime_storage` | true | keep | already true (O_NOATIME) |
| `incoming_starts_queued_torrents` | false | keep | queueing off |
| `report_true_downloaded` | false | keep | tracker accounting; leave tracker-compatible default |
| `strict_end_game_mode` | true | **patched** | request the last blocks from several peers (end-game of a race) |
| `enable_outgoing_utp` | true | set by qBittorrent | see the qBittorrent table |
| `enable_incoming_utp` | true | set by qBittorrent | see the qBittorrent table |
| `enable_outgoing_tcp` | true | set by qBittorrent | see the qBittorrent table |
| `enable_incoming_tcp` | true | set by qBittorrent | see the qBittorrent table |
| `ignore_resume_timestamps` | false | keep | safety on restart |
| `no_recheck_incomplete_resume` | false | keep | safety on restart |
| `anonymous_mode` | false | set by qBittorrent | see the qBittorrent table |
| `report_web_seed_downloads` | true | keep | not used in this setup |
| `seeding_outgoing_connections` | true | keep | true: seeds dial out to leechers - essential for racing upload |
| `no_connect_privileged_ports` | false | set by qBittorrent | see the qBittorrent table |
| `smooth_connects` | true | **patched** | allow connection bursts at race start |
| `always_send_user_agent` | false | keep | tracker whitelists check the client id; keep default |
| `apply_ip_filter_to_trackers` | true | set by qBittorrent | see the qBittorrent table |
| `ban_web_seeds` | true | keep | not used in this setup |
| `allow_partial_disk_writes` | true | keep | true lets writes start before a whole cache line is full |
| `support_share_mode` | true | keep | not used in this setup |
| `support_merkle_torrents` | true | keep | not used in this setup |
| `report_redundant_bytes` | true | keep | tracker accounting; default |
| `listen_system_port_fallback` | true | set by qBittorrent | see the qBittorrent table |
| `announce_crypto_support` | true | keep | only advertises the extension; no cost |
| `enable_upnp` | true | set by qBittorrent | see the qBittorrent table |
| `enable_natpmp` | true | set by qBittorrent | see the qBittorrent table |
| `enable_lsd` | true | set by qBittorrent | see the qBittorrent table |
| `enable_dht` | true | set by qBittorrent | see the qBittorrent table |
| `prefer_rc4` | false | set by qBittorrent | see the qBittorrent table |
| `proxy_hostnames` | true | set by qBittorrent | see the qBittorrent table |
| `proxy_peer_connections` | true | set by qBittorrent | see the qBittorrent table |
| `auto_sequential` | true | keep | only kicks in when there are more peers than pieces left; harmless |
| `proxy_tracker_connections` | true | keep | no proxy |
| `enable_ip_notifier` | true | keep | reacts to address changes; harmless on a static server |
| `dht_prefer_verified_node_ids` | true | keep | DHT security |
| `piece_extent_affinity` | false | set by qBittorrent | see the qBittorrent table |
| `validate_https_trackers` | true | set by qBittorrent | see the qBittorrent table |
| `ssrf_mitigation` | true | set by qBittorrent | see the qBittorrent table |
| `allow_idna` | false | set by qBittorrent | see the qBittorrent table |
| `tracker_completion_timeout` | 30 | keep | 30 s is fine for announce |
| `tracker_receive_timeout` | 10 | keep | 10 s is fine for announce |
| `stop_tracker_timeout` | 5 | set by qBittorrent | see the qBittorrent table |
| `tracker_maximum_response_length` | 1024*1024 | keep | 1 MiB is plenty |
| `piece_timeout` | 20 | **patched** | re-request stalled pieces sooner |
| `request_timeout` | 60 | **patched** | re-request stalled blocks sooner |
| `request_queue_time` | 3 | **patched** | deeper pipeline to fast high-RTT peers |
| `max_allowed_in_request_queue` | 500 | **patched** | fast leechers may pipeline 32 MiB (HPS; libtorrent 2.0 default) |
| `max_out_request_queue` | 500 | set by qBittorrent | see the qBittorrent table |
| `whole_pieces_threshold` | 20 | keep | fast peers already get whole pieces (piece < 20 s of their rate); good for 16 MiB racing pieces |
| `peer_timeout` | 120 | keep | 120 s = protocol keep-alive interval; HPS 20 s would drop legal idle peers on long-term seeds |
| `urlseed_timeout` | 20 | keep | not used in this setup |
| `urlseed_pipeline_size` | 5 | keep | not used in this setup |
| `urlseed_wait_retry` | 30 | keep | not used in this setup |
| `file_pool_size` | 40 | set by qBittorrent | see the qBittorrent table |
| `max_failcount` | 3 | **patched** | racing swarms are flaky; keep peers a bit longer before giving up |
| `min_reconnect_time` | 60 | **patched** | retry dropped peers sooner |
| `peer_connect_timeout` | 15 | **patched** | free half-open slots faster |
| `connection_speed` | 30 | set by qBittorrent | see the qBittorrent table |
| `inactivity_timeout` | 600 | keep | same reason as peer_timeout |
| `unchoke_interval` | 15 | keep | unlimited unchoke slots: interested peers are unchoked immediately |
| `optimistic_unchoke_interval` | 30 | keep | unlimited unchoke slots |
| `num_want` | 200 | keep | 200 is the protocol max most trackers honour (private trackers cap lower) |
| `initial_picker_threshold` | 4 | keep | random first pieces give something to trade quickly |
| `allowed_fast_set_size` | 5 | **patched** | everyone is unchoked anyway (HPS) |
| `suggest_mode` | settings_pack::no_piece_suggestions | set by qBittorrent | see the qBittorrent table |
| `max_queued_disk_bytes` | 1024 * 1024 | set by qBittorrent | see the qBittorrent table |
| `handshake_timeout` | 10 | keep | 10 s |
| `send_buffer_low_watermark` | 10 * 1024 | set by qBittorrent | see the qBittorrent table |
| `send_buffer_watermark` | 500 * 1024 | set by qBittorrent | see the qBittorrent table |
| `send_buffer_watermark_factor` | 50 | set by qBittorrent | see the qBittorrent table |
| `choking_algorithm` | settings_pack::fixed_slots_choker | set by qBittorrent | see the qBittorrent table |
| `seed_choking_algorithm` | settings_pack::round_robin | set by qBittorrent | see the qBittorrent table |
| `cache_size` | 2048 | set by qBittorrent | see the qBittorrent table |
| `cache_expiry` | 300 | set by qBittorrent | see the qBittorrent table |
| `disk_io_write_mode` | settings_pack::enable_os_cache | set by qBittorrent | see the qBittorrent table |
| `disk_io_read_mode` | settings_pack::enable_os_cache | set by qBittorrent | see the qBittorrent table |
| `outgoing_port` | 0 | set by qBittorrent | see the qBittorrent table |
| `num_outgoing_ports` | 0 | set by qBittorrent | see the qBittorrent table |
| `peer_dscp` | 0x04 | set by qBittorrent | see the qBittorrent table |
| `active_downloads` | 3 | set by qBittorrent | see the qBittorrent table |
| `active_seeds` | 5 | set by qBittorrent | see the qBittorrent table |
| `active_checking` | 1 | set by qBittorrent | see the qBittorrent table |
| `active_dht_limit` | 88 | set by qBittorrent | see the qBittorrent table |
| `active_tracker_limit` | 1600 | set by qBittorrent | see the qBittorrent table |
| `active_lsd_limit` | 60 | set by qBittorrent | see the qBittorrent table |
| `active_limit` | 500 | set by qBittorrent | see the qBittorrent table |
| `auto_manage_interval` | 30 | keep | queueing off |
| `seed_time_limit` | 24 * 60 * 60 | keep | queueing off |
| `auto_scrape_interval` | 1800 | set by qBittorrent | see the qBittorrent table |
| `auto_scrape_min_interval` | 300 | set by qBittorrent | see the qBittorrent table |
| `max_peerlist_size` | 3000 | keep | 3000 known peers per torrent is far above any private swarm |
| `max_paused_peerlist_size` | 1000 | keep | paused torrents |
| `min_announce_interval` | 5 * 60 | keep | tracker sanity floor; trackers dictate the interval |
| `auto_manage_startup` | 60 | set by qBittorrent | see the qBittorrent table |
| `seeding_piece_quota` | 20 | keep | round-robin seed choker only |
| `max_rejects` | 50 | **patched** | HPS |
| `recv_socket_buffer_size` | 0 | set by qBittorrent | see the qBittorrent table |
| `send_socket_buffer_size` | 0 | set by qBittorrent | see the qBittorrent table |
| `max_peer_recv_buffer_size` | 2 * 1024 * 1024 | **patched** | HPS |
| `read_cache_line_size` | 32 | keep | 512 KiB read-ahead per miss = HPS value; seeding reads mostly hit page cache |
| `write_cache_line_size` | 16 | **patched** | flush 4 MiB at a time (HPS; matches RAID stripes) |
| `optimistic_disk_retry` | 10 * 60 | keep | error handling |
| `max_suggest_pieces` | 16 | keep | memory bound for received suggests |
| `local_service_announce_interval` | 5 * 60 | keep | LSD off |
| `dht_announce_interval` | 15 * 60 | keep | DHT not used by private torrents |
| `udp_tracker_token_expiry` | 60 | keep | BEP 15 value |
| `num_optimistic_unchoke_slots` | 0 | keep | unlimited unchoke slots |
| `default_est_reciprocation_rate` | 16000 | keep | BitTyrant choker only |
| `increase_est_reciprocation_rate` | 20 | keep | BitTyrant choker only |
| `decrease_est_reciprocation_rate` | 3 | keep | BitTyrant choker only |
| `max_pex_peers` | 50 | keep | PEX is disabled on private torrents |
| `tick_interval` | 500 | **patched** | faster rate / request-queue adaptation |
| `share_mode_target` | 3 | keep | not used in this setup |
| `upload_rate_limit` | 0 | set by qBittorrent | see the qBittorrent table |
| `download_rate_limit` | 0 | set by qBittorrent | see the qBittorrent table |
| `dht_upload_rate_limit` | 8000 | keep | DHT traffic only |
| `unchoke_slots_limit` | 8 | set by qBittorrent | see the qBittorrent table |
| `connections_limit` | 200 | set by qBittorrent | see the qBittorrent table |
| `connections_slack` | 10 | keep | connection limit is 20000; never reached |
| `utp_target_delay` | 100 | keep | TCP only |
| `utp_gain_factor` | 3000 | keep | TCP only |
| `utp_min_timeout` | 500 | keep | TCP only |
| `utp_syn_resends` | 2 | keep | TCP only |
| `utp_fin_resends` | 2 | keep | TCP only |
| `utp_num_resends` | 3 | keep | TCP only |
| `utp_connect_timeout` | 3000 | keep | TCP only |
| `utp_delayed_ack` | 0 | keep | TCP only |
| `utp_loss_multiplier` | 50 | keep | TCP only |
| `mixed_mode_algorithm` | settings_pack::peer_proportional | set by qBittorrent | see the qBittorrent table |
| `listen_queue_size` | 5 | set by qBittorrent | see the qBittorrent table |
| `torrent_connect_boost` | 30 | **patched** | connect to the whole first announce immediately |
| `alert_queue_size` | 1000 | set by qBittorrent | see the qBittorrent table |
| `max_metadata_size` | 3 * 1024 * 10240 | keep | magnet metadata cap |
| `checking_mem_usage` | 1024 | set by qBittorrent | see the qBittorrent table |
| `predictive_piece_announce` | 0 | **patched** | HAVE just before a piece completes |
| `aio_threads` | 4 | set by qBittorrent | see the qBittorrent table |
| `tracker_backoff` | 250 | keep | failing-tracker retry curve; autobrr re-announces on its own |
| `share_ratio_limit` | 200 | keep | queueing off |
| `seed_time_ratio_limit` | 700 | keep | queueing off |
| `peer_turnover` | 4 | set by qBittorrent | see the qBittorrent table |
| `peer_turnover_cutoff` | 90 | set by qBittorrent | see the qBittorrent table |
| `peer_turnover_interval` | 300 | set by qBittorrent | see the qBittorrent table |
| `connect_seed_every_n_download` | 10 | keep | connection_speed 500/s is never the bottleneck |
| `max_http_recv_buffer_size` | 4*1024*204 | keep | tracker / .torrent download size cap |
| `max_retry_port_bind` | 10 | set by qBittorrent | see the qBittorrent table |
| `alert_mask` | int(static_cast<std::uint32_t>(alert_category::error)) | set by qBittorrent | see the qBittorrent table |
| `out_enc_policy` | settings_pack::pe_enabled | set by qBittorrent | see the qBittorrent table |
| `in_enc_policy` | settings_pack::pe_enabled | set by qBittorrent | see the qBittorrent table |
| `allowed_enc_level` | settings_pack::pe_both | set by qBittorrent | see the qBittorrent table |
| `inactive_down_rate` | 2048 | set by qBittorrent | see the qBittorrent table |
| `inactive_up_rate` | 2048 | set by qBittorrent | see the qBittorrent table |
| `proxy_type` | settings_pack::none | set by qBittorrent | see the qBittorrent table |
| `proxy_port` | 0 | set by qBittorrent | see the qBittorrent table |
| `i2p_port` | 0 | set by qBittorrent | see the qBittorrent table |
| `cache_size_volatile` | 256 | keep | volatile blocks = hash-check reads; not on the racing path |
| `urlseed_max_request_bytes` | 16 * 1024 * 1024 | keep | not used in this setup |
| `web_seed_name_lookup_retry` | 1800 | keep | not used in this setup |
| `close_file_interval` | CLOSE_FILE_INTERVAL | keep | 0 on Linux (Windows-only workaround) |
| `utp_cwnd_reduce_timer` | 100 | keep | TCP only |
| `max_web_seed_connections` | 3 | keep | not used in this setup |
| `resolver_cache_timeout` | 1200 | set by qBittorrent | see the qBittorrent table |
| `send_not_sent_low_watermark` | 16384 | **patched** | per-socket TCP_NOTSENT_LOWAT (HPS) |
| `rate_choker_initial_threshold` | 1024 | keep | rate-based choker not used |
| `upnp_lease_duration` | 3600 | set by qBittorrent | see the qBittorrent table |
| `max_concurrent_http_announces` | 50 | set by qBittorrent | see the qBittorrent table |
