#!/usr/bin/env python3
"""Local BitTorrent engine lab: candidate vs fixed peers across a veth link with netem latency.

  lab.py setup                       create netns 'qbtlat' + veth (10.200.0.1 <-> 10.200.0.2) + 25 ms each way
  lab.py teardown
  lab.py run <test> <candidate> <label>
      test: download  candidate leecher (in netns) <- 4 fixed seeders (host)
            upload    candidate seeder (host, cold cache) -> 4 fixed leechers (netns)
"""
import json, os, re, shutil, signal, subprocess, sys, time, urllib.parse, urllib.request

LAB = "/home/brooke/qbtlab"; BIN = f"{LAB}/bin"; TORRENT = f"{LAB}/lab.torrent"; DATA = f"{LAB}/data"
NS = "qbtlat"; HOST_IP = "10.200.0.1"; NS_IP = "10.200.0.2"; DELAY = "25ms"
FIXED_SEED = "tuned-znver4"; FIXED_LEECH = "stock-v1.2.20"; NPEERS = int(os.environ.get("NPEERS", "4"))

CANDIDATES = {   # name -> (binary, extra config lines)
    "tuned-znver4":    ("tuned-znver4", []),
    "tuned-generic":   ("tuned-generic", []),
    "stock-v1":        ("stock-v1.2.20", []),
    "stock-v2-mmap":   ("stock-v2.0.15", ["Session\\DiskIOType=Default", "Session\\HashingThreadsCount=4"]),
    "stock-v2-pread":  ("stock-v2.0.15", ["Session\\DiskIOType=SimplePreadPwrite", "Session\\HashingThreadsCount=4"]),
    "labenv": ("tuned-labenv", []), "final3": ("tuned-final3", []), "final2": ("tuned-final2", []), "final2-encoff": ("tuned-final2", ["Session\\Encryption=2"]),
    "v2-pread-encoff": ("stock-v2.0.15", ["Session\\DiskIOType=SimplePreadPwrite", "Session\\HashingThreadsCount=4", "Session\\Encryption=2"]),
    "v2-mmap-encoff": ("stock-v2.0.15", ["Session\\DiskIOType=Default", "Session\\HashingThreadsCount=4", "Session\\Encryption=2"]),
    "final": ("tuned-final", []), "final-encoff": ("tuned-final", ["Session\\Encryption=2"]),
    "cross": ("tuned-cross", []), "cross-encoff": ("tuned-cross", ["Session\\Encryption=2"]),
    "vA": ("tuned-vA", []), "vB": ("tuned-vB", []), "vC": ("tuned-vC", []),
    "vA-encoff": ("tuned-vA", ["Session\\Encryption=2"]), "vC-encoff": ("tuned-vC", ["Session\\Encryption=2"]),
    "stock-v1-encoff": ("stock-v1.2.20", ["Session\\Encryption=2"]),
}
COMMON = r"""Session\AsyncIOThreadsCount=16
Session\BTProtocol=TCP
Session\CheckingMemUsageSize=1024
Session\ConnectionSpeed=500
Session\DHTEnabled=false
Session\DiskCacheSize=4096
Session\DiskQueueSize=67108864
Session\FilePoolSize=5000
Session\LSDEnabled=false
Session\MaxConnections=20000
Session\MaxConnectionsPerTorrent=-1
Session\MaxUploads=-1
Session\MaxUploadsPerTorrent=-1
Session\MultiConnectionsPerIp=true
Session\PeXEnabled=false
Session\PieceExtentAffinity=true
Session\Preallocation=true
Session\QueueingSystemEnabled=false
Session\RequestQueueSize=1500
Session\SendBufferLowWatermark=3072
Session\SendBufferWatermark=20480
Session\SendBufferWatermarkFactor=200
Session\SocketBacklogSize=3000
Session\SuggestMode=true"""


def sh(*a, check=True):
    return subprocess.run(a, check=check, capture_output=True, text=True)


def setup():
    teardown()
    sh("ip", "netns", "add", NS)
    sh("ip", "link", "add", "vh", "type", "veth", "peer", "name", "vn")
    sh("ip", "link", "set", "vn", "netns", NS)
    sh("ip", "addr", "add", f"{HOST_IP}/24", "dev", "vh"); sh("ip", "link", "set", "vh", "up", "mtu", "1500")
    for c in (["ip", "addr", "add", f"{NS_IP}/24", "dev", "vn"], ["ip", "link", "set", "vn", "up", "mtu", "1500"],
              ["ip", "link", "set", "lo", "up"]):
        sh("ip", "netns", "exec", NS, *c)
    sh("tc", "qdisc", "add", "dev", "vh", "root", "netem", "delay", DELAY, "limit", "1000000")
    sh("ip", "netns", "exec", NS, "tc", "qdisc", "add", "dev", "vn", "root", "netem", "delay", DELAY, "limit", "1000000")
    for k, v in (("net.ipv4.tcp_congestion_control", "bbr"), ("net.core.rmem_max", "67108864"), ("net.core.wmem_max", "67108864"),
                 ("net.ipv4.tcp_rmem", "4096 87380 67108864"), ("net.ipv4.tcp_wmem", "4096 65536 67108864")):
        sh("ip", "netns", "exec", NS, "sysctl", "-qw", f"{k}={v}")
    rtt = sh("ip", "netns", "exec", NS, "ping", "-c", "3", "-q", HOST_IP).stdout
    print("netns ready:", re.search(r"= [\d.]+/([\d.]+)/", rtt).group(1), "ms RTT")


def teardown():
    stop_all()
    sh("ip", "link", "del", "vh", check=False); sh("ip", "netns", "del", NS, check=False)


def stop_all():
    subprocess.run(["pkill", "-u", "brooke", "-f", f"{BIN}/"], capture_output=True)
    for _ in range(40):
        if subprocess.run(["pgrep", "-u", "brooke", "-f", f"{BIN}/"], capture_output=True).returncode: return
        time.sleep(0.25)
    subprocess.run(["pkill", "-9", "-u", "brooke", "-f", f"{BIN}/"], capture_output=True)


class Inst:
    def __init__(self, name, binary, in_ns, webport, btport, extra=()):
        self.name, self.binary, self.in_ns, self.webport, self.btport = name, binary, in_ns, webport, btport
        self.dir = f"{LAB}/run/{name}"; self.ip = NS_IP if in_ns else "127.0.0.1"
        shutil.rmtree(self.dir, ignore_errors=True); os.makedirs(f"{self.dir}/profile/qBittorrent/config")
        os.makedirs(f"{self.dir}/dl")
        over = {e.split("=", 1)[0] for e in extra}
        common = "\n".join(l for l in COMMON.splitlines() if l.split("=", 1)[0] not in over)
        conf = (f"[BitTorrent]\nSession\\Port={btport}\n{common}\n" + "".join(e + "\n" for e in extra) +
                f"\n[LegalNotice]\nAccepted=true\n\n[Preferences]\nWebUI\\Address=*\nWebUI\\Port={webport}\n"
                "WebUI\\LocalHostAuth=false\nWebUI\\AuthSubnetWhitelistEnabled=true\nWebUI\\AuthSubnetWhitelist=10.200.0.0/24\n"
                "WebUI\\HostHeaderValidation=false\nWebUI\\CSRFProtection=false\n")
        open(f"{self.dir}/profile/qBittorrent/config/qBittorrent.conf", "w").write(conf)
        subprocess.run(["chown", "-R", "brooke:brooke", f"{LAB}/run"], check=True)

    def start(self):
        cmd = ["runuser", "-u", "brooke", "--", "setsid", f"{BIN}/{self.binary}", f"--profile={self.dir}/profile",
               "--confirm-legal-notice"]
        if self.in_ns: cmd = ["ip", "netns", "exec", NS] + cmd
        subprocess.Popen(cmd, stdout=open(f"{self.dir}/run.log", "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def api(self, path, data=None, timeout=10):
        url = f"http://{self.ip}:{self.webport}/api/v2{path}"
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data is not None else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read(); return json.loads(b) if b[:1] in (b"[", b"{") else b.decode()

    def wait_ready(self):
        for _ in range(120):
            try: self.api("/app/version", timeout=2); return
            except Exception: time.sleep(0.25)
        raise RuntimeError(f"{self.name} did not start")

    def add(self, savepath, seed):
        body, ctype = multipart({"savepath": savepath, "skip_checking": "true" if seed else "false",
                                 "autoTMM": "false"}, open(TORRENT, "rb").read())
        req = urllib.request.Request(f"http://{self.ip}:{self.webport}/api/v2/torrents/add", data=body,
                                     headers={"Content-Type": ctype})
        urllib.request.urlopen(req, timeout=20).read()
        for _ in range(80):
            ts = self.api("/torrents/info")
            if ts: return ts[0]["hash"]
            time.sleep(0.25)
        raise RuntimeError(f"{self.name}: torrent not added")

    def pid(self):
        out = subprocess.run(["pgrep", "-u", "brooke", "-f", f"profile={self.dir}/profile"], capture_output=True, text=True).stdout.split()
        return int(out[0]) if out else None


def multipart(fields, torrent):
    b = "----qbtlab"; parts = []
    for k, v in fields.items():
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"torrents\"; filename=\"lab.torrent\"\r\n"
                 "Content-Type: application/x-bittorrent\r\n\r\n".encode() + torrent + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def cpu_s(pid):
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
    return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")


def hwm_mb(pid):
    m = re.search(r"VmHWM:\s+(\d+)", open(f"/proc/{pid}/status").read()); return int(m.group(1)) // 1024


def run(test, cand, label):
    binary, extra = CANDIDATES[cand]
    stop_all(); shutil.rmtree(f"{LAB}/run", ignore_errors=True)
    ncand = 2 if test.endswith("2") else 1; base = test.rstrip("2")
    if base == "download":
        cands = [Inst(f"cand{j}", binary, True, 18200 + j, 52000 + j, extra) for j in range(ncand)]
        fixed = [Inst(f"seed{i}", FIXED_SEED, False, 18210 + i, 52010 + i) for i in range(NPEERS)]
    else:
        cands = [Inst(f"cand{j}", binary, False, 18200 + j, 52000 + j, extra) for j in range(ncand)]
        fixed = [Inst(f"leech{i}", FIXED_LEECH, True, 18210 + i, 52010 + i) for i in range(NPEERS)]
    for i in cands + fixed: i.start()
    for i in cands + fixed: i.wait_ready()
    if base == "download":
        for s in fixed: s.add(DATA, seed=True)
        subprocess.run(["sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
        peers = "|".join(f"{HOST_IP}:{s.btport}" for s in fixed)
        targets = [(c, c.add(f"{c.dir}/dl", seed=False), peers) for c in cands]; watch = cands
    else:
        for c in cands: c.add(DATA, seed=True)
        subprocess.run(["sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"])
        hs = [l.add(f"{l.dir}/dl", seed=False) for l in fixed]; watch = fixed
        # leecher i pulls from candidate (i % ncand)
        targets = [(l, hh, f"{HOST_IP}:{cands[i % ncand].btport}") for i, (l, hh) in enumerate(zip(fixed, hs))]
    time.sleep(1)
    pids = [c.pid() for c in cands]; c0 = sum(cpu_s(p) for p in pids); t0 = time.time()
    for inst, hh, peers in targets: inst.api("/torrents/addPeers", {"hashes": hh, "peers": peers})
    done_at = {}; deadline = t0 + int(os.environ.get("LAB_DEADLINE", "400"))
    while len(done_at) < len(watch) and time.time() < deadline:
        for w in watch:
            if w.name in done_at: continue
            try:
                t = w.api("/torrents/info")[0]
                if t["progress"] >= 1.0: done_at[w.name] = time.time() - t0
            except Exception: pass
        time.sleep(0.25)
    el = max(done_at.values()) if len(done_at) == len(watch) else None
    c1 = sum(cpu_s(p) for p in pids); mem = sum(hwm_mb(p) for p in pids)
    gb = 20 * 1024 ** 3 * len(watch) / 1e9
    res = {"test": test, "cand": cand, "label": label, "seconds": round(el, 1) if el else None,
           "GBps": round(gb / el, 2) if el else None, "cand_cpu_s": round(c1 - c0, 1),
           "cpu_s_per_GB": round((c1 - c0) / gb, 2), "cand_peak_rss_MB": mem, "finished": len(done_at)}
    print(json.dumps(res), flush=True)
    stop_all(); shutil.rmtree(f"{LAB}/run", ignore_errors=True)
    return res


def set_delay(d):
    sh("tc", "qdisc", "change", "dev", "vh", "root", "netem", "delay", d, "limit", "1000000")
    sh("ip", "netns", "exec", NS, "tc", "qdisc", "change", "dev", "vn", "root", "netem", "delay", d, "limit", "1000000")
    rtt = sh("ip", "netns", "exec", NS, "ping", "-c", "3", "-q", HOST_IP).stdout
    print("RTT now", re.search(r"= [\d.]+/([\d.]+)/", rtt).group(1), "ms")


if __name__ == "__main__":
    if sys.argv[1] == "delay":
        set_delay(sys.argv[2])
    elif sys.argv[1] in ("setup", "teardown"):
        {"setup": setup, "teardown": teardown}[sys.argv[1]]()
    else:
        # lab.py run <test> <cand> <label> [--set Key=Value ...]
        sets = [a.split("=", 1) for a in sys.argv[5:] if "=" in a]
        if sets:
            b, extra = CANDIDATES[sys.argv[3]]
            name = sys.argv[3] + "+" + ",".join(f"{k.split(chr(92))[-1]}={v}" for k, v in sets)
            CANDIDATES[name] = (b, extra + [f"Session\\{k}={v}" if "\\" not in k else f"{k}={v}" for k, v in sets])
            run(sys.argv[2], name, sys.argv[4])
        else:
            run(*sys.argv[2:5])
