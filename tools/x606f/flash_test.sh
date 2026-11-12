#!/bin/sh
# 在电脑上刷入测试镜像 (需要 fastboot, 平板进 fastboot/bootloader 模式)
#   ./flash_test.sh try                      fastboot boot (LK 不支持会报错)
#   ./flash_test.sh recovery boot_test.img   刷到 recovery 分区, 不动 boot
#   ./flash_test.sh restore recovery.img     还原原厂 recovery (采集包里 partitions/recovery.img)
# 进入 recovery 模式: 关机后按住 音量+ 与电源键 (或 adb reboot recovery)
set -eu
case "${1:-}" in
  try)      fastboot boot "${2:-boot_test.img}" ;;
  recovery) printf "将 %s 刷入 recovery 分区? [y/N] " "${2:?需要 boot_test.img}"; read a; [ "$a" = y ] && fastboot flash recovery "$2" ;;
  restore)  fastboot flash recovery "${2:?需要原厂 recovery.img}" ;;
  *) sed -n '2,7p' "$0"; exit 1 ;;
esac
