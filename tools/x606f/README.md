# TB-X606F (MT6765 / MT8768WT) 主线 bring-up 第一阶段

## 仓库里新增 / 修改的文件
| 路径 | 说明 |
|---|---|
| `arch/arm64/boot/dts/mediatek/mt6765-lenovo-tb-x606f.dts` | 最小设备树 (GIC-v3、sysirq、timer、PSCI、8×A53、UART0、LK 帧缓冲、真实 RAM 布局) |
| `arch/arm64/boot/dts/mediatek/Makefile` | 修改: 加 `dtb-$(CONFIG_ARCH_MEDIATEK) += mt6765-lenovo-tb-x606f.dtb` 和 `DTC_FLAGS_...` 两行 |
| `arch/arm64/configs/x606f.config` | 内核配置片段, 配合 defconfig 使用 |
| `.github/workflows/build-x606f.yml` | GitHub Actions: 自动编译 Image.gz + DTB + initramfs, 打包 boot_test.img |
| `tools/x606f/x606f_bootpack.py` | boot.img(header v2) 打包/解包 + MTK DTB 表封装 |
| `tools/x606f/mk_initramfs.sh`, `tools/x606f/init` | 生成 aarch64 静态 busybox 最小 initramfs |
| `tools/x606f/flash_test.sh` | 电脑上用 fastboot 刷入测试镜像 |

## 本地编译 (可选)
```
make ARCH=arm64 defconfig x606f.config
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image.gz mediatek/mt6765-lenovo-tb-x606f.dtb
tools/x606f/mk_initramfs.sh initramfs.cpio.gz     # 需要 docker
python3 tools/x606f/x606f_bootpack.py pack -o boot_test.img \
  --kernel arch/arm64/boot/Image.gz --ramdisk initramfs.cpio.gz \
  --dtb arch/arm64/boot/dts/mediatek/mt6765-lenovo-tb-x606f.dtb \
  --cmdline "bootopt=64S3,32N2,64N2 buildvariant=user earlycon=uart8250,mmio32,0x11002000 console=ttyS0,921600n8 console=tty0 ignore_loglevel keep_bootcon clk_ignore_unused pd_ignore_unused rdinit=/init"
```

## 重要: 内核加载偏移
原厂 boot.img 的 kernel_offset 是 0x80000 (旧内核 text_offset)。主线 arm64 镜像头里 text_offset 为 0, 要求加载地址 **2MB 对齐**,
所以打包默认用 `--kernel-offset 0x200000`。如果仍然黑屏无串口, 再试 `--kernel-offset 0x0`。

## 测试 (保证不变砖)
1. 采集包里的 `partitions/` 先备份两份。
2. 只把测试镜像刷进 **recovery** 分区 (`flash_test.sh recovery boot_test.img`), 不动 boot。
3. 关机后按 音量+ 与电源键进 recovery 模式; 正常开机仍是原厂系统。
4. 还原: `flash_test.sh restore recovery.img`。

## 现象对照
- 屏幕出现 `TB-X606F mainline ... init OK` 和心跳 → 全部正常
- 能看到内核日志但颜色/错位 → 改 DTS 里 simple-framebuffer 的 `stride`(4864/4800) 和 `format`
- 完全黑屏且无串口 → 试 `--kernel-offset 0x0`、`--raw-dtb`, 再检查内存区间

## 内核 7.3.4 里已有的 MT6765 支持 (第二阶段可直接用)
`clk-mt6765*` (topckgen/infracfg/apmixedsys/mm/img/cam/vcodec/audio)、`pinctrl-mt6765`、`mtk-pmic-wrap`(mt6765)、
`mtk-sd`(借 mt8183 compat)、`mediatek,mt6765-uart`、`mediatek,mt6765-sysirq`。
