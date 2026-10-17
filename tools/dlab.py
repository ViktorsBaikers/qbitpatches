#!/usr/bin/env python3
"""Deluge in the lab: the production container image + config, against the same fixed qBittorrent peers as lab.py.

  dlab.py run <download|upload> <variant> <label>

The candidate runs on the host side (docker bridge network like production, or --network host); the fixed peers
(8 by default via NPEERS) run in the netns behind 50 ms RTT. Variant "qbit:<lab candidate>" runs a lab.py
qBittorrent candidate in the same orientation for reference.
"""
import base64, copy, json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pylib"))
import lab
from deluge_client import DelugeRPCClient

IMAGE = "dlab/deluge:prod"          # linuxserver/deluge:libtorrentv1 @ the digest production runs
SRC = "/root/qbt-tuning/deluge"     # core.prod.json, ltconfig.prod.json, plugins/
NET = "dlabnet"; CNAME = "dlab-cand"; BT = 52100; RPC = 52146
SYSCTLS = ["net.ipv4.tcp_slow_start_after_idle=0", "net.ipv4.tcp_mtu_probing=1", "net.core.somaxconn=65535",
           "net.ipv4.tcp_max_syn_backlog=65536", "net.ipv4.tcp_fin_timeout=10", "net.ipv4.tcp_tw_reuse=1",
           "net.ipv4.tcp_fastopen=3", "net.ipv4.ip_local_port_range=1024 65535"]   # production compose

ENC_OFF_CORE = {"enc_in_policy": 2, "enc_out_policy": 2}
ENC_OFF_LT = {"in_enc_policy": 2, "out_enc_policy": 2}
FIX_CORE = {"stop_seed_at_ratio": False, "random_outgoing_ports": True}
TUNED_LT = {
    "max_out_request_queue": 1500, "max_allowed_in_request_queue": 2000, "tick_interval": 250,
    "piece_timeout": 10, "request_timeout": 20, "peer_timeout": 120, "inactivity_timeout": 600,
    "min_reconnect_time": 10, "max_failcount": 5, "use_parole_mode": True, "whole_pieces_threshold": 20,
    "initial_picker_threshold": 4, "handshake_timeout": 10, "peer_connect_timeout": 10, "aio_threads": 16,
    "write_cache_line_size": 256, "enable_incoming_utp": False, "send_not_sent_low_watermark": 524288,
    "predictive_piece_announce": 20, "file_pool_size": 5000,
}
# variant -> (network, core overrides, ltconfig overrides)
VARIANTS = {
    "prod":         ("bridge", {}, {}),
    "prod-ratiofix": ("bridge", {"stop_seed_at_ratio": False}, {}),
    "encoff":       ("bridge", {**FIX_CORE, **ENC_OFF_CORE}, ENC_OFF_LT),
    "tuned":        ("bridge", {**FIX_CORE, **ENC_OFF_CORE}, {**ENC_OFF_LT, **TUNED_LT}),
    "tuned-host":   ("host", {**FIX_CORE, **ENC_OFF_CORE}, {**ENC_OFF_LT, **TUNED_LT}),
    "tuned-encon":  ("bridge", FIX_CORE, TUNED_LT),
    "tuned-pea":    ("bridge", {**FIX_CORE, **ENC_OFF_CORE}, {**ENC_OFF_LT, **TUNED_LT, "piece_extent_affinity": True}),
}


def load_conf(path):   # deluge config files are two concatenated JSON objects: header + body
    s = open(path).read(); body = s[s.index("}") + 1:]
    return json.loads(body)


def write_conf(path, body):
    open(path, "w").write('{\n    "file": 1,\n    "format": 1\n}' + json.dumps(body, indent=4, sort_keys=True))


def variant_spec(variant):
    """'<variant>' or '<variant>+lt:key,key' (adds those keys' TUNED_LT values on top, for bisecting)."""
    if "+lt:" not in variant:
        return VARIANTS[variant]
    base, keys = variant.split("+lt:", 1)
    net, core_over, lt_over = VARIANTS[base]
    return net, core_over, {**lt_over, **{k: TUNED_LT[k] for k in keys.split(",")}}


class Deluge:
    def __init__(self, variant):
        variant, _, tag = variant.partition("@")          # '<variant>@<tag>' runs image dlab/deluge:<tag>
        self.image = f"dlab/deluge:{tag}" if tag else IMAGE
        self.net, core_over, lt_over = variant_spec(variant)
        self.name = "cand0"; self.dir = f"{lab.LAB}/run/{self.name}"; self.btport = BT
        shutil.rmtree(self.dir, ignore_errors=True); os.makedirs(f"{self.dir}/config/plugins"); os.makedirs(f"{self.dir}/dl")
        core = load_conf(f"{SRC}/core.prod.json")
        core.update(core_over)
        core.update({"listen_ports": [BT, BT], "daemon_port": RPC, "allow_remote": True, "new_release_check": False,
                     "download_location": f"{self.dir}/dl", "enabled_plugins": ["ltConfig"],
                     "plugins_location": "/config/plugins", "torrentfiles_location": "/config/torrents",
                     "autoadd_location": "/config/watch"})
        write_conf(f"{self.dir}/config/core.conf", core)
        ltc = load_conf(f"{SRC}/ltconfig.prod.json"); ltc["settings"].update(lt_over)
        write_conf(f"{self.dir}/config/ltconfig.conf", ltc)
        open(f"{self.dir}/config/auth", "w").write("lab:lab:10\n")
        for f in os.listdir(f"{SRC}/plugins"): shutil.copy(f"{SRC}/plugins/{f}", f"{self.dir}/config/plugins/")
        subprocess.run(["chown", "-R", "1000:1000", f"{lab.LAB}/run"], check=True)
        self.client = None

    def start(self):
        subprocess.run(["docker", "rm", "-f", CNAME], capture_output=True)
        cmd = ["docker", "run", "-d", "--name", CNAME, "--user", "1000:1000", "--entrypoint", "/lsiopy/bin/deluged",
               "-e", "HOME=/config", "-e", "PYTHON_EGG_CACHE=/config/plugins/.python-eggs",
               "--ulimit", "nofile=2097152:2097152",
               "-v", f"{self.dir}/config:/config", "-v", f"{lab.LAB}:{lab.LAB}"]
        if self.net == "host":
            cmd += ["--network", "host"]
        else:
            cmd += ["--network", NET, "-p", f"{BT}:{BT}", "-p", f"{BT}:{BT}/udp", "-p", f"127.0.0.1:{RPC}:{RPC}"]
            for s in SYSCTLS: cmd += ["--sysctl", s]
        cmd += [self.image, "-c", "/config", "-d", "-L", "info", "-l", "/config/deluged.log"]
        subprocess.run(cmd, check=True, capture_output=True)

    def wait_ready(self):
        for _ in range(120):
            try:
                c = DelugeRPCClient("127.0.0.1", RPC, "lab", "lab", decode_utf8=True); c.connect()
                if "ltConfig" in c.call("core.get_enabled_plugins"):
                    self.client = c; time.sleep(2); return    # let ltConfig apply its settings
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError("deluged did not start")

    def add(self, savepath, seed):
        dump = base64.b64encode(open(lab.TORRENT, "rb").read()).decode()
        tid = self.client.call("core.add_torrent_file", "lab.torrent", dump,
                               {"download_location": savepath, "seed_mode": seed, "add_paused": False})
        self.tid = tid; return tid

    def add_peers(self, _hash, peers):
        for p in peers.split("|"):
            ip, port = p.rsplit(":", 1); self.client.call("core.connect_peer", self.tid, ip, int(port))

    def status(self):
        return self.client.call("core.get_torrent_status", self.tid, ["progress", "state", "upload_payload_rate"])

    def progress(self):
        return self.status()["progress"] / 100.0

    def pid(self):
        return int(subprocess.run(["docker", "inspect", "-f", "{{.State.Pid}}", CNAME], capture_output=True,
                                  text=True).stdout.strip())

    def stop(self):
        subprocess.run(["docker", "rm", "-f", CNAME], capture_output=True)


class QbtCand(lab.Inst):
    """lab.py qBittorrent candidate on the host side, same orientation as the Deluge candidate."""
    def __init__(self, cand):
        binary, extra = lab.CANDIDATES[cand]
        super().__init__("cand0", binary, False, 18200, BT, extra)

    def add_peers(self, h, peers):
        self.api("/torrents/addPeers", {"hashes": h, "peers": peers})

    def progress(self):
        return self.api("/torrents/info")[0]["progress"]

    def stop(self):
        pass


def qbt_progress(inst):
    return inst.api("/torrents/info")[0]["progress"]


def run(test, variant, label):
    stop()
    if subprocess.run(["docker", "network", "inspect", NET], capture_output=True).returncode:
        subprocess.run(["docker", "network", "create", NET], check=True, capture_output=True)
    cand = QbtCand(variant.split(":", 1)[1]) if variant.startswith("qbit:") else Deluge(variant)
    peers_bin = lab.FIXED_SEED if test == "download" else lab.FIXED_LEECH
    fixed = [lab.Inst(f"{'seed' if test == 'download' else 'leech'}{i}", peers_bin, True, 18210 + i, 52010 + i)
             for i in range(lab.NPEERS)]
    for i in [cand] + fixed: i.start()
    for i in [cand] + fixed: i.wait_ready()
    if test == "download":
        for s in fixed: s.add(lab.DATA, seed=True)
        subprocess.run(["sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
        h = cand.add(f"{cand.dir}/dl", seed=False)
        time.sleep(1); pid = cand.pid(); c0 = lab.cpu_s(pid); t0 = time.time()
        cand.add_peers(h, "|".join(f"{lab.NS_IP}:{s.btport}" for s in fixed))
        watch = [("cand", cand.progress)]
    else:
        cand.add(lab.DATA, seed=True)
        subprocess.run(["sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
        hs = [l.add(f"{l.dir}/dl", seed=False) for l in fixed]
        time.sleep(1); pid = cand.pid(); c0 = lab.cpu_s(pid); t0 = time.time()
        for l, h in zip(fixed, hs): l.api("/torrents/addPeers", {"hashes": h, "peers": f"{lab.HOST_IP}:{BT}"})
        watch = [(l.name, (lambda l=l: qbt_progress(l))) for l in fixed]
    done_at = {}; deadline = t0 + int(os.environ.get("LAB_DEADLINE", "900")); last = {}
    while len(done_at) < len(watch) and time.time() < deadline:
        for name, prog in watch:
            if name in done_at: continue
            try:
                p = prog(); last[name] = p
                if p >= 1.0: done_at[name] = time.time() - t0
            except Exception:
                pass
        time.sleep(0.25)
    el = max(done_at.values()) if len(done_at) == len(watch) else None
    c1 = lab.cpu_s(pid); mem = lab.hwm_mb(pid)
    extra = {}
    if isinstance(cand, Deluge):
        try: extra["cand_state"] = cand.status()["state"]
        except Exception: pass
    gb = 20 * 1024 ** 3 * len(watch) / 1e9
    res = {"test": test, "cand": f"deluge:{variant}" if not variant.startswith("qbit:") else variant, "label": label,
           "npeers": lab.NPEERS, "seconds": round(el, 1) if el else None, "GBps": round(gb / el, 2) if el else None,
           "cand_cpu_s": round(c1 - c0, 1), "cpu_s_per_GB": round((c1 - c0) / gb, 2), "cand_peak_rss_MB": mem,
           "finished": len(done_at), "progress_at_end": {k: round(v, 3) for k, v in last.items()}, **extra}
    print(json.dumps(res), flush=True)
    cand.stop(); stop()
    return res


def stop():
    subprocess.run(["docker", "rm", "-f", CNAME], capture_output=True)
    lab.stop_all(); shutil.rmtree(f"{lab.LAB}/run", ignore_errors=True)


if __name__ == "__main__":
    run(*sys.argv[2:5])
