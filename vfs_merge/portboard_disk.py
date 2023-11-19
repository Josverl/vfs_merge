"""
This file contains information about the flash layout of the various ports, and specifically 
- the start of the filesystem
- the size of the filesystem
- the version of littlefs to use (lfs1, lfs2)

This makes it possible to create a littlefs image for a specific port, and to merge that image with the firmware

See the portboard_disk.md file to understand how/where to retrieve the information
"""
from dataclasses import dataclass
from typing import List

# rp2_common
FLASH_PAGE_SIZE = 256
FLASH_SECTOR_SIZE = 4096  # :=> LittleFS Block

# lfs versions used by micropython
VFS_LFS1 = 0x0001_0000
VFS_LFS2 = 0x0002_0000

# common flash block size for littlefs
VFLASH_BLOCK_SIZE = 4096


# todo: add more ports and boards
# todo: low - add type of filesystem (lfs1, lfs2, fatfs)


@dataclass
class PortDiskInfo:
    name: str
    version: str = ""
    flash_size: int = 0
    page_size: int = 256
    block_size: int = VFLASH_BLOCK_SIZE
    block_count: int = 0
    start_address: int = 0
    end_address: int = 0
    image_size: int = 0
    vfstype: int = VFS_LFS2

    def __post_init__(self):
        assert self.block_size > 0, "block_size must be > 0"
        assert self.page_size > 0, "page_size must be > 0"
        # CALC image size
        if self.start_address and self.end_address:
            self.image_size = self.end_address - self.start_address
            self.block_count = self.image_size // self.block_size
        elif self.start_address and self.image_size:
            self.block_count = self.image_size // self.block_size
            self.end_address = self.start_address + self.image_size
        elif self.block_count and not self.image_size:
            self.image_size = self.block_size * self.block_count
        assert self.image_size > 0, "image_size must be > 0"
        assert self.block_count > 0, "block_count must be > 0"
        assert self.start_address, "drive start_address must be provided"


port_info_list: List[PortDiskInfo] = [
    PortDiskInfo(
        "esp32-generic",
        start_address=0x0020_0000,
        image_size=0x0020_0000,
        flash_size=0x40_0000,
    ),  # 4MB
    # pico_w = 0x1012c000-0x10200000 (848K)
    PortDiskInfo(
        "rp2-pico_w",
        start_address=0x1012_C000,
        end_address=0x1020_0000,
    ),  

    # Below ports & boards are not yet verified
    PortDiskInfo(
        "esp32-ota",
        start_address=0x0031_0000,
        image_size=0x000F_0000,
        flash_size=0x40_0000,
    ),  # 4MB-OTA
    PortDiskInfo(
        "esp32-s3-generic",
        start_address=0x0020_0000,
        image_size=0x0060_0000,
        flash_size=0x80_0000,
    ),  # 8MB
    PortDiskInfo(
        "rp2-pico",
        start_address=0x100A_0000,
        end_address=0x1020_0000,
    ),  # (1408K):
    PortDiskInfo(
        "pimoroni_picolipo_16mb",
        start_address=0x1010_0000,
        end_address=0x1100_0000,
    )
    # pimoroni_picolipo_16mb = 0x10100000-0x11000000 (15360K)
    # PortDiskInfo("esp8266-generic", 256, VFLASH_BLOCK_SIZE, 512),
    # PortDiskInfo("SAMD", 1536, VFLASH_BLOCK_SIZE, 512),
]
