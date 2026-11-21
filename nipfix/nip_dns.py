#!/usr/bin/env python3
"""nip-dns: 极简 nip 风格 DNS 服务器 (纯 stdlib, UDP)。

解析规则: <8位hex>.<ZONE>  →  A 记录 = hex 解码出的 IPv4
  例: ZONE=nip.example.com 时, ac40e5bb.nip.example.com → 172.64.229.187
      (与 edgetunnel bestip 页面的 hex 编码一致: 每字节 2 位 hex, 共 8 位)
其余同名查询 → NXDOMAIN。

用法:
  NIP_ZONE=nip.foxleoly.link NIP_PORT=5353 python3 nip_dns.py
生产建议: NIP_PORT=53, 放 docker/systemd, 前面加个 53→53 转发或直接用 53。
"""
import os, re, socket, struct, sys, time

ZONE = os.environ.get("NIP_ZONE", "nip.example.com").lower().rstrip(".")
PORT = int(os.environ.get("NIP_PORT", "5353"))
TTL = int(os.environ.get("NIP_TTL", "300"))
HEX8 = re.compile(r"^([0-9a-f]{8})\.(" + re.escape(ZONE) + r")$")


def decode_name(data: bytes, off: int):
    """解析 DNS name (处理指针压缩), 返回 (name, new_off)。"""
    labels, seen_ptr = [], False
    while True:
        ln = data[off]
        if ln == 0:
            off += 1
            break
        if ln & 0xC0 == 0xC0:  # pointer
            if not seen_ptr:
                ptr = struct.unpack(">H", data[off:off + 2])[0] & 0x3FFF
                seen_ptr = True
                off = ptr  # 跟到指针处继续解析
                continue
            else:
                off += 2
                break
        labels.append(data[off + 1:off + 1 + ln].decode("ascii", "replace"))
        off += 1 + ln
    return ".".join(labels).lower(), off


def build_response(qid: int, qname: str, qtype: int, ip_hex, rcode: int = 0) -> bytes:
    # header: ID, FLAGS(AA|RD|RA | rcode), QD=1, AN=1/0, NS=0, AR=0
    flags = 0x8180 | (rcode & 0xF)
    # question section
    q = qname.encode()
    qsection = b"".join(bytes([len(p)]) + p.encode() for p in qname.split(".")) + b"\x00"
    qsection += struct.pack(">HH", qtype, 1)
    ancount = 0
    asection = b""
    if ip_hex:
        ancount = 1
        # answer: NAME(ptr 0xC00C) TYPE=1 CLASS=1 TTL RDLENGTH RDATA
        rdata = bytes(int(ip_hex[i:i + 2], 16) for i in range(0, 8, 2))
        asection = struct.pack(">HHHIH", 0xC00C, 1, 1, TTL, 4) + rdata
    header = struct.pack(">HHHHHH", qid, flags, 1, ancount, 0, 0)
    return header + qsection + asection


def handle(data: bytes, addr):
    qid, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    if qd == 0:
        return None
    name, off = decode_name(data, 12)
    qtype, qclass = struct.unpack(">HH", data[off:off + 4])
    m = HEX8.match(name)
    in_zone = name == ZONE or name.endswith("." + ZONE)
    if not in_zone:
        # zone 外 → REFUSED (5), 让递归 resolver 走别处
        return build_response(qid, name, qtype, None, rcode=5)
    if m and qtype in (1, 255):
        ip_hex = m.group(1)
        ip = socket.inet_ntoa(bytes(int(ip_hex[i:i + 2], 16) for i in range(0, 8, 2)))
        print(f"[{time.strftime('%H:%M:%S')}] {name} -> {ip}", flush=True)
        return build_response(qid, name, qtype, ip_hex)
    # zone 内但不是 hex8 → NXDOMAIN (3)
    print(f"[{time.strftime('%H:%M:%S')}] {name} -> NXDOMAIN", flush=True)
    return build_response(qid, name, qtype, None, rcode=3)


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", PORT))
    print(f"nip-dns listening on :{PORT} zone=<{ZONE}>  (hex8.{ZONE} -> IP)", flush=True)
    while True:
        data, addr = s.recvfrom(512)
        resp = handle(data, addr)
        if resp:
            s.sendto(resp, addr)


if __name__ == "__main__":
    main()
