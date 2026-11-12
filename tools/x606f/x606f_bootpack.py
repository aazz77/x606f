#!/usr/bin/env python3
"""
x606f_bootpack.py - TB-X606F (MT6765) 的 boot.img 打包 / 解包工具, 纯 Python, 无第三方依赖。

参数默认值全部来自你设备上原厂 boot.img 的头部:
  header_version=2  page_size=2048  base=0x40000000
  (原厂 kernel_offset=0x80000, 但主线内核要求 2MB 对齐, 打包默认改为 0x200000)
  ramdisk_offset=0x11b00000
  tags_offset=0x7880000  dtb_addr=0x47880000
  cmdline="bootopt=64S3,32N2,64N2 buildvariant=user"
原厂的 kernel / ramdisk 都是裸 gzip (没有 MTK 512 字节头), dtb 是 MTK 的 DTB 表
(魔数 0xd7b7ab1e, 里面只有 1 个 dtb)。

子命令:
  unpack  boot.img 输出目录        解包出 kernel / ramdisk / dtb(.dtb 表和裸 dtb) / header.json
  dtbtable in.dtb out.dtbtable     把裸 dtb 包成 MTK DTB 表 (LK 吃这个格式)
  pack    -o boot.img ...          打包 (见 --help)
"""
import argparse, hashlib, json, os, struct, sys

MAGIC = b"ANDROID!"
MTK_DTB_MAGIC = 0xD7B7AB1E


def pad(data: bytes, page: int) -> bytes:
    r = (-len(data)) % page
    return data + b"\0" * r


def dtb_table(dtb: bytes) -> bytes:
    """裸 dtb -> MTK DTB 表 (单个条目, 和原厂格式一致: 头 32 字节, 条目 32 字节, 数据从 64 开始)"""
    if dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit("输入不是裸 FDT (魔数不是 d00dfeed)")
    hdr_size, entry_size, count, entries_off, page, ver = 32, 32, 1, 32, 2048, 0
    data_off = hdr_size + entry_size
    total = data_off + len(dtb)
    hdr = struct.pack(">8I", MTK_DTB_MAGIC, total, hdr_size, entry_size, count, entries_off, page, ver)
    entry = struct.pack(">8I", len(dtb), data_off, 0, 0, 0, 0, 0, 0)
    return hdr + entry + dtb


def cmd_dtbtable(a):
    open(a.out, "wb").write(dtb_table(open(a.inp, "rb").read()))
    print("写出", a.out)


def parse_header(d: bytes):
    if d[:8] != MAGIC:
        raise SystemExit("不是 Android boot.img")
    (ks, ka, rs, ra, ss, sa, ta, ps, hv, osv) = struct.unpack("<10I", d[8:48])
    h = dict(kernel_size=ks, kernel_addr=ka, ramdisk_size=rs, ramdisk_addr=ra,
             second_size=ss, second_addr=sa, tags_addr=ta, page_size=ps,
             header_version=hv, os_version=osv,
             name=d[48:64].split(b"\0")[0].decode(),
             cmdline=(d[64:576].split(b"\0")[0] + d[608:1632].split(b"\0")[0]).decode())
    if hv >= 1:
        h["recovery_dtbo_size"], h["recovery_dtbo_offset"], h["header_size"] = struct.unpack("<IQI", d[1632:1648])
    if hv >= 2:
        h["dtb_size"], h["dtb_addr"] = struct.unpack("<IQ", d[1648:1660])
    return h


def cmd_unpack(a):
    d = open(a.img, "rb").read()
    h = parse_header(d)
    ps = h["page_size"]
    os.makedirs(a.outdir, exist_ok=True)
    off = ps

    def take(n):
        nonlocal off
        blob = d[off:off + n]
        off += (n + ps - 1) // ps * ps
        return blob

    k = take(h["kernel_size"])
    r = take(h["ramdisk_size"])
    s = take(h["second_size"])
    rdo = take(h.get("recovery_dtbo_size", 0))
    dtb = take(h.get("dtb_size", 0))
    for name, blob in (("kernel", k), ("ramdisk", r), ("second", s), ("recovery_dtbo", rdo), ("dtb_table", dtb)):
        if blob:
            open(os.path.join(a.outdir, name), "wb").write(blob)
    if dtb[:4] == struct.pack(">I", MTK_DTB_MAGIC):
        esz, cnt, eoff = struct.unpack(">3I", dtb[12:24])   # entry_size, count, entries_offset
        for i in range(cnt):
            sz, o = struct.unpack(">2I", dtb[eoff + i * esz: eoff + i * esz + 8])
            open(os.path.join(a.outdir, "dtb%d.dtb" % i), "wb").write(dtb[o:o + sz])
    json.dump(h, open(os.path.join(a.outdir, "header.json"), "w"), indent=2)
    print(json.dumps(h, indent=2))


def cmd_pack(a):
    base = int(a.base, 0)
    ps = a.pagesize
    kernel = open(a.kernel, "rb").read()
    ramdisk = open(a.ramdisk, "rb").read() if a.ramdisk else b""
    dtb = open(a.dtb, "rb").read() if a.dtb else b""
    if dtb and dtb[:4] == b"\xd0\x0d\xfe\xed" and not a.raw_dtb:
        dtb = dtb_table(dtb)            # 默认包成 MTK DTB 表, 和原厂一致
    cmdline = a.cmdline.encode()
    if len(cmdline) > 1536:
        raise SystemExit("cmdline 太长")
    kaddr = base + int(a.kernel_offset, 0)
    raddr = base + int(a.ramdisk_offset, 0)
    taddr = base + int(a.tags_offset, 0)
    dtb_addr = base + int(a.dtb_offset, 0)
    osv = a.os_version
    h = MAGIC + struct.pack("<10I", len(kernel), kaddr, len(ramdisk), raddr, 0, base + 0xF00000,
                            taddr, ps, 2, osv)
    h += a.name.encode().ljust(16, b"\0")[:16]
    h += cmdline[:512].ljust(512, b"\0")
    sha = hashlib.sha1()
    for blob in (kernel, ramdisk, b"", b"", dtb):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))
    h += (sha.digest() + b"\0" * 12)[:32]
    h += cmdline[512:].ljust(1024, b"\0")
    h += struct.pack("<IQI", 0, 0, 1660)      # recovery_dtbo(size, offset), header_size
    h += struct.pack("<IQ", len(dtb), dtb_addr)
    assert len(h) == 1660, len(h)
    out = pad(h, ps) + pad(kernel, ps) + pad(ramdisk, ps) + pad(dtb, ps)
    open(a.output, "wb").write(out)
    print("写出 %s  (%d 字节)  kernel@%#x ramdisk@%#x tags/dtb@%#x" % (a.output, len(out), kaddr, raddr, dtb_addr))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    u = sp.add_parser("unpack"); u.add_argument("img"); u.add_argument("outdir"); u.set_defaults(f=cmd_unpack)
    t = sp.add_parser("dtbtable"); t.add_argument("inp"); t.add_argument("out"); t.set_defaults(f=cmd_dtbtable)

    k = sp.add_parser("pack", help="打包 header v2 的 boot.img")
    k.add_argument("-o", "--output", required=True)
    k.add_argument("--kernel", required=True, help="Image.gz 或 Image (arm64)")
    k.add_argument("--ramdisk", help="initramfs (cpio.gz); 不给则空")
    k.add_argument("--dtb", required=True, help="裸 dtb; 默认自动包成 MTK DTB 表")
    k.add_argument("--raw-dtb", action="store_true", help="不包 MTK DTB 表, 直接放裸 dtb")
    k.add_argument("--cmdline", default="bootopt=64S3,32N2,64N2 buildvariant=user")
    k.add_argument("--base", default="0x40000000")
    k.add_argument("--kernel-offset", default="0x200000",
                   help="主线 arm64 内核镜像头 text_offset=0, 要求 2MB 对齐, 所以不能用原厂的 0x80000")
    k.add_argument("--ramdisk-offset", default="0x11b00000")
    k.add_argument("--tags-offset", default="0x7880000")
    k.add_argument("--dtb-offset", default="0x7880000")
    k.add_argument("--pagesize", type=int, default=2048)
    k.add_argument("--os-version", type=lambda x: int(x, 0), default=335544649,
                   help="原厂值 335544649 (Android 10 / 补丁日期)")
    k.add_argument("--name", default="")
    k.set_defaults(f=cmd_pack)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
