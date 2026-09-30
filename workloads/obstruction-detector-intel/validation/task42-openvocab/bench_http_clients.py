# This project was developed with assistance from AI tools.
"""curl does this request in ~175 ms, requests takes ~950 ms. Find a Python
client path that closes the gap, since the detector is Python.
"""
import http.client
import statistics
import time

import requests
import urllib3

N = 6
with open("/work/body.bin", "rb") as fh:
    body = fh.read()
with open("/work/hlen.txt") as fh:
    hlen = fh.read().strip()
HOST, PORT, PATH = "fastsam-rest", 8081, "/v2/models/fastsam/infer"
H = {"Content-Type": "application/octet-stream",
     "Inference-Header-Content-Length": hlen}

def timeit(fn, label):
    fn()  # warm
    ts = []
    for _ in range(N):
        t0 = time.perf_counter()
        n = fn()
        ts.append((time.perf_counter() - t0) * 1000)
    print(f"{label:<34} median={statistics.median(ts):7.1f}ms  min={min(ts):7.1f}ms  bytes={n}")

def f_requests():
    r = requests.post(f"http://{HOST}:{PORT}{PATH}", data=body, headers=H, timeout=300)
    return len(r.content)

sess = requests.Session()
def f_session():
    r = sess.post(f"http://{HOST}:{PORT}{PATH}", data=body, headers=H, timeout=300)
    return len(r.content)

pool = urllib3.PoolManager(maxsize=4)
def f_urllib3():
    r = pool.request("POST", f"http://{HOST}:{PORT}{PATH}", body=body, headers=H,
                     preload_content=True)
    return len(r.data)

conn = http.client.HTTPConnection(HOST, PORT, timeout=300)
def f_httpclient():
    conn.request("POST", PATH, body=body, headers=H)
    resp = conn.getresponse()
    data = resp.read()
    return len(data)

timeit(f_requests,   "requests.post (new conn)")
timeit(f_session,    "requests Session")
timeit(f_urllib3,    "urllib3 PoolManager")
timeit(f_httpclient, "http.client (stdlib, keep-alive)")
