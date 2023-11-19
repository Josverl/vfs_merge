# How to get the information for a port:

## esp32:

the esp32 port uses the partition table to get the information about the partitions.
The partition table is defined in the `partitions.csv` file in the `ports/esp32` directory.

[ports/esp32/partitions-4MiB.csv](https://github.com/micropython/micropython/blob/master/ports/esp32/partitions-4MiB.csv):
```csv
# Notes: the offset of the partition table itself is set in
# $IDF_PATH/components/partition_table/Kconfig.projbuild.
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x6000,
phy_init, data, phy,     0xf000,  0x1000,
factory,  app,  factory, 0x10000, 0x1F0000,
vfs,      data, fat,     0x200000, 0x200000,
```

The relevant part is the line with the `vfs` entry.   
The `vfs` entry defines the start address and the size of the partition.
 - The **start_address** is the Offset.
 - the **image_size** is the Size.

The corresponding definition in portboard_disk.py is:  
``` python
    PortDiskInfo(
        "esp32-generic",
        start_address=0x0020_0000,
        image_size=0x0020_0000,
        flash_size=0x40_0000,
    ),  # 4MB
```

## rp2:

For rp2 binaries the simples way is to make use of the information in the uf2 file.
This is also what the vfs_merge tool already tries to do 

- use  the `picotool info --all <filename.uf2>` command to show the information:
``` log
Program Information
 name:            MicroPython
 version:         v1.20.0
...
 binary start:    0x10000000
 binary end:      0x1004de88
 embedded drive:  0x100a0000-0x10200000 (1408K): MicroPython
...
Build Information
 sdk version:       1.5.0
 pico_board:        pico

```
Then you can use the values in `embedded drive:  0x100a0000-0x10200000 (1408K)` to add the ports's disk information to the diskportinfo.py file.
The naming convention for the name of the port is the `<port>-<board>` value. This is commonly (_but not always_) used as a prefix in the MicroPython prebuilt binaries: `rp2-pico-20230426-v1.20.0.uf2`.


```python
    PortDiskInfo(
        "rp2-pico",
        start_address=0x100A_0000,
        end_address=0x1020_0000,
    ),  # (1408K):
```

## other ports 
I've not yet looked at other ports.
The ports that use a `.uf2` file should be able to use an approach similar to the `rp2`.

The difficult part will be to determine the** starting address** and **size** for the file system for each specific port, board and version.
