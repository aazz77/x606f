#!/bin/sh
# 生成 aarch64 静态 busybox initramfs: ./mk_initramfs.sh <输出 cpio.gz>
# 需要 docker (GitHub Actions 的 ubuntu runner 自带); 只是从镜像里复制 busybox, 不需要 qemu
set -eu
OUT=${1:?用法: mk_initramfs.sh <输出 cpio.gz>}
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
mkdir -p "$W/root/bin" "$W/root/dev" "$W/root/proc" "$W/root/sys" "$W/root/etc"

docker create --platform linux/arm64 --name x606f-bb busybox:musl >/dev/null
docker cp x606f-bb:/bin/busybox "$W/root/bin/busybox"
docker rm x606f-bb >/dev/null
chmod 755 "$W/root/bin/busybox"
file "$W/root/bin/busybox" 2>/dev/null || true

for a in sh ls cat echo mount umount dmesg sleep cut grep uname setsid ps free df ip reboot poweroff; do
  ln -sf busybox "$W/root/bin/$a"
done
install -m 755 "$HERE/init" "$W/root/init"

( cd "$W/root" && find . | cpio -o -H newc 2>/dev/null | gzip -9 ) > "$OUT"
rm -rf "$W"
echo "initramfs: $OUT ($(wc -c < "$OUT") bytes)"
