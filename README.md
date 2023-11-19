# vfs_merge
Merge a MicroPython firmware and with source files into a single binary that can be flashed to a device.


Merge 
 - the files in `src/**/*` 
 - with the firmware in `firmware/<firmware.bin/uf2>` 
 
 and write the resulting firmware image to : 
    - `build/firmware.bin` or `build/firmware.uf2`:

## Esp32 
`vfsmerge --port esp32 --firmware ./firmware`
``` log


INFO      | Micropython Port: esp32
INFO      | Source folder path: src
INFO      | Firmware path: firmware\ESP32_GENERIC-20231005-v1.21.0.bin
INFO      | Build path: build
INFO      | Create littlefs image: build\littlefs.img
DEBUG     | Create new filesystem with: 512 blocks of 4096 bytes = 2048Kb
INFO      | Add files from src
DEBUG     | Adding /foo.py
DEBUG     | Adding /main.py
DEBUG     | Adding /lib/bar.py
DEBUG     | write filesystem to build\littlefs.img
INFO      | Merge firmware and littlefs image into build\firmware_lfs.bin
DEBUG     | running: esptool --chip esp32 merge_bin -o build\firmware_lfs.bin --flash_mode dio --flash_size 4MB 0x1000 firmware\ESP32_GENERIC-20231005-v1.21.0.bin 0x00200000 build\littlefs.img
esptool.py v4.6.2
Wrote 0x400000 bytes to file build\firmware_lfs.bin, ready to flash to offset 0x0
```

## RP2 Pico_W
`vfsmerge --port rp2-pico_w  --firmware .\firmware\rp2-pico-w-20230426-v1.20.0.uf2`

``` log

INFO      | Micropython Port: rp2-pico_w
INFO      | Source folder path: src
INFO      | Firmware path: firmware\rp2-pico-w-20230426-v1.20.0.uf2
INFO      | Build path: build
INFO      | Create littlefs image: build\littlefs.img
DEBUG     | Create new filesystem with: 212 blocks of 4096 bytes = 848Kb
INFO      | Add files from src
DEBUG     | Adding /foo.py
DEBUG     | Adding /main.py
DEBUG     | Adding /lib/bar.py
DEBUG     | write filesystem to build\littlefs.img
DEBUG     | Running D:\MyPython\vfs_merge\vfs_merge\picotool info -a firmware\rp2-pico-w-20230426-v1.20.0.uf2
DEBUG     | Number of blocks: 2736
Program name: MicroPython
Board: pico_w
Number of families: 1
 - Family RP2040 at 0x1000_0000
Number of ranges: 1
 - Range 0: 0x1000_0000 - 0x100A_B000
LittleFS superblocks: 0
Pico drive info
 - Drive start: 0x1012_C000
 - Drive end: 0x1020_0000

INFO      | Reading littlefs binary image from build\littlefs.img
DEBUG     | Extend uf2 with: 3392 blocks
DEBUG     | LittleFS image size: 3392 blocks
INFO      | Writing 3392 blocks to littlefs.uf2
INFO      |  > Found LittleFS file system header in block 2736 at 0x1012_C000
INFO      |  > Found LittleFS file system header in block 2752 at 0x1012_D000
DEBUG     | Writing 6128 blocks to build\firmware_lfs.uf2
DEBUG     | Number of blocks: 6128
Program name: MicroPython
Board: pico_w
Number of families: 1
 - Family RP2040 at 0x1000_0000
Number of ranges: 2
 - Range 0: 0x1000_0000 - 0x100A_B000
 - Range 1: 0x1012_C000 - 0x1020_0000
LittleFS superblocks: 2
 - LittleFS superblock 0: block 2736 at 0x1012_C000
 - LittleFS superblock 1: block 2752 at 0x1012_D000
Pico drive info
 - Drive start: 0x1012_C000
 - Drive end: 0x1020_0000

```