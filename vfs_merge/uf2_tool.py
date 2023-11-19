#!/usr/bin/python3
""" uf2_info.py 

Display information of the UF2 file.
- display information on the different parts of the UF2file
- find little fs file system in the UF2 file
- find the different ranges in the UF2 file
- find the different families in the UF2 file
- find the binary information in the UF2 file ( rp2040 only, using picotool ) 

"""

import argparse
import ctypes
import os
import re
import struct
import subprocess
import sys
from collections import UserList
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loguru import logger as log

from .portboard_disk import port_info_list
from .uf2conv import UF2_MAGIC_START0  # is_uf2,
from .uf2conv import UF2_MAGIC_END, UF2_MAGIC_START1, load_families

# --------------------------------------------------------------
# UF2 file format
# --------------------------------------------------------------
UF2_NOFLASH = 0x00000001
# If set, the block is "comment" and should not be flashed to the device
UF2_FILE_CONTAINER = 0x00001000
UF2_FAMILY_ID_PRESENT = 0x00002000
# when set, the fileSize/familyID holds a value identifying the board family (usually corresponds to an MCU)
# The current master list of family IDs is maintained in a JSON file.
UF2_MD5_PRESENT = 0x00004000
# when set, the md5 hash of the file is present in the file container
UF2_EXTENSION_TAGS_PRESENT = 0x00008000
# when set, the file container contains tags

UF2_BLOCK_SIZE = 512
UF2_DATA_SIZE = 476  # 512 - 32 - 4

flag_descriptions = {
    UF2_NOFLASH: "Do not flash to device",
    UF2_FILE_CONTAINER: "File container",
    UF2_FAMILY_ID_PRESENT: "Family ID present",
    UF2_MD5_PRESENT: "MD5 hash present",
    UF2_EXTENSION_TAGS_PRESENT: "Extension tags present",
}

try:
    KNOWN_FAMILIES = load_families()
except FileNotFoundError:
    log.warning("Families file not found")
    KNOWN_FAMILIES = {}


# Used to find the start of the littlefs file system
LITTLEFS_MARKER = b"\xF0\x0F\xFF\xF7littlefs/\xE0\x00\x10"


class UF2Block(ctypes.LittleEndianStructure):
    """A block in a UF2 file with the following structure:"""

    _pack_ = 1
    _fields_: list[tuple[str, type]] = [
        ("magicStart0", ctypes.c_uint32),  # 0
        ("magicStart1", ctypes.c_uint32),  # 1
        ("flags", ctypes.c_uint32),  # 2
        ("targetAddr", ctypes.c_uint32),  # 3
        ("payloadSize", ctypes.c_uint32),  # 4
        ("blockNo", ctypes.c_uint32),  # 5
        ("numBlocks", ctypes.c_uint32),  # 6
        ("reserved", ctypes.c_uint32),  # 7
        ("data", ctypes.c_uint8 * UF2_DATA_SIZE),
        ("magicEnd", ctypes.c_uint32),  # -1
    ]

    def __init__(self, data: Optional[bytes] = None):
        """Create a UF2 block from a bytes object"""
        super().__init__()
        self.magicStart0 = UF2_MAGIC_START0
        self.magicStart1 = UF2_MAGIC_START1
        self.magicEnd = UF2_MAGIC_END
        if data:
            if len(data) > UF2_DATA_SIZE:
                raise ValueError(f"Data too long: {len(data)}")
            # copy the data to the data field, padded with 0x00
            self.data = (ctypes.c_uint8 * UF2_DATA_SIZE).from_buffer_copy(data + b"\0" * (UF2_DATA_SIZE - len(data)))

    @property
    def is_uf2_block(self):
        """Check if the block is a valid UF2 block"""
        return self.magicStart0 == UF2_MAGIC_START0 and self.magicStart1 == UF2_MAGIC_START1 and self.magicEnd == UF2_MAGIC_END

    def __str__(self) -> str:
        """Return a string representation of the UF2 block - specifically the flags"""
        result = ""
        result += f" - blockNo={self.blockNo}\n"
        result += f" - flags={self.flags:0b}\n"
        for flag_value, flag_description in flag_descriptions.items():
            if flag_value & self.flags:
                if flag_value == UF2_FAMILY_ID_PRESENT:
                    result += f"   - {flag_description} : 0x{self.reserved:_X}\n"
                else:
                    result += f"   - {flag_description}\n"
        result += f" - payloadSize={self.payloadSize}\n"
        result += f" - numBlocks={self.numBlocks}\n"
        return result


class UF2File(UserList):
    """A representations of a UF2 file with the following
    Attributes:

    - file_path: the path to the uf2 file
    - data: a list of UF2 blocks, can be accessed as a list or with the [] operator
    - families: a dictionary of families and their addresses
    - ranges: a list of tuples (start, end) of the different ranges in the file
    - littlefs_superblocks: list of blocknumbers where the littlefs file system starts

    - board: the board name (rp2 only)
    - program_name: the name of the program (rp2 only)
    - binary_start: the start address of the binary (rp2 only)
    - binary_end: the end address of the binary (rp2 only)
    - drive_start: the start address of the drive (rp2 only, or littlefs detected)
    - drive_end: the end address of the drive (rp2 only)

    Methods:
    - read_uf2: read the uf2 file and populate the data attribute
    - scan: scan the data attribute for the different parts of the uf2 file
    - scan_family_names: scan the data attribute for the different families
    - scan_ranges: scan the data attribute for the different ranges
    - scan_littlefs: scan the data attribute for the littlefs file system
    - add_bin_info: read the binary information using picotool and add the information to the class (rp2 only)
    - get_family_name: get the family name from the family hex value

    List operations:
    - getitem: get a UF2 block from the data attribute
    - len: return the number of blocks in the data attribute
    - append: append a UF2 block to the data attribute
    - extend: extend the data attribute with a list of UF2 blocks
    - insert: insert a UF2 block at a specific index in the data attribute


    """

    def __init__(self, iterable=None):
        if iterable is None:
            iterable = []
        super().__init__(str(item) for item in iterable)
        self.data = []
        self.families: Dict[str, int] = {}
        self.littlefs_superblocks = []
        # list of blocknumbers where the littlefs file system starts
        self.ranges = []
        # list of tuples (start, end) of the different ranges in the file

        self.program_name = ""
        self.binary_start = 0
        self.binary_end = 0
        self.drive_start = 0
        self.drive_end = 0
        self.board = ""
        # appstartaddr = 0x2000

    @property
    def family_str(self) -> str:
        """Return the family name of the first family found in the file"""
        fl = list(self.families.keys())
        return fl[0] if fl else ""

    @property
    def family_id(self) -> int:  # type: ignore
        """Return the family id of the first family found in the file"""
        KNOWN_FAMILIES[self.family_str] if self.family_str in KNOWN_FAMILIES.keys() else 0

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __setitem__(self, index, item: UF2Block):
        self.data[index] = item

    def insert(self, index, item: UF2Block):
        self.data.insert(index, item)

    def read_uf2(self, filepath: Path):
        "Read a UF2 file and populate the blocks and scan for information"
        self.file_path = filepath
        with open(filepath, "rb") as f:
            while True:
                data = f.read(ctypes.sizeof(UF2Block))
                if not data:
                    break
                block = UF2Block.from_buffer_copy(data)
                if not block.is_uf2_block:
                    log.warning(f"Skipping block {block.blockNo}; bad magic")
                    continue
                self.data.append(block)
        self.scan()

    def append(self, block: UF2Block):
        "append a UF2 block to the data attribute"
        if self.data and block.targetAddr < self.data[-1].targetAddr + self.data[-1].payloadSize:
            raise ValueError(f"Block {block.blockNo} at 0x{block.targetAddr:08_X} is before the last block")
        block.blockNo = len(self.data)
        self.data.append(block)

    def extend(self, other: Iterable[UF2Block]):
        "extend the data attribute with a list of UF2 blocks"
        for block in other:
            self.append(block)

    def __str__(self) -> str:
        result = ""
        # blocks
        result += f"Number of blocks: {len(self)}\n"
        result += f"Program name: {self.program_name}\n"
        result += f"Board: {self.board}\n"
        # familiy
        result += f"Number of families: {len(self.families)}\n"
        for family, addr in self.families.items():
            result += f" - Family {family} at 0x{addr:08_X}\n"
        # ranges
        result += f"Number of ranges: {len(self.ranges)}\n"
        for i, (start, end) in enumerate(self.ranges):
            result += f" - Range {i}: 0x{start:08_X} - 0x{end:08_X}\n"
        # Drives
        # LittleFS
        result += f"LittleFS superblocks: {len(self.littlefs_superblocks)}\n"
        for i, blockno in enumerate(self.littlefs_superblocks):
            result += f" - LittleFS superblock {i}: block {blockno} at 0x{self.data[blockno].targetAddr:08_X}\n"
        result += "Pico drive info\n"
        result += f" - Drive start: 0x{self.drive_start:08_X}\n"
        result += f" - Drive end: 0x{self.drive_end:08_X}\n"
        return result

    def get_family_name(self, family_hex):
        """Get the family name using the family hex value"""
        family_short_name = "unknown"
        for name, value in KNOWN_FAMILIES.items():
            if value == family_hex:
                family_short_name = name
        return family_short_name

    def scan(self):
        """scan the data attribute for the different parts of the uf2 file"""
        self.scan_family_names()
        self.scan_ranges()
        self.scan_littlefs()

    def scan_ranges(self):
        "scan the blocks for the start of the different ranges"
        # a range is a series of blocks withouth padding in between
        self.ranges = []
        last_address = 0
        start_range = 0
        end_range = 0
        # iterate over the blocks and check if the block is a range start or end    # add the start and end addresses of the range to the ranges list
        for block in self.data:
            if start_range == 0:
                # first block in range
                start_range = block.targetAddr
            elif last_address != block.targetAddr or block.data[: block.payloadSize] == b"\x00" * block.payloadSize:
                # gap detected or end of range
                # block is all 0x00, end of range
                end_range = last_address
                self.ranges.append((start_range, end_range))
                start_range = block.targetAddr
                end_range = 0

            last_address = block.targetAddr + block.payloadSize
        # add the last range
        end_range = last_address
        self.ranges.append((start_range, end_range))

    def scan_littlefs(self):
        for block in self.data:
            if block.targetAddr % 4096 == 0 and LITTLEFS_MARKER in bytes(block.data):
                log.info(f" > Found LittleFS file system header in block {block.blockNo} at 0x{block.targetAddr:08_X}")
                self.littlefs_superblocks.append(block.blockNo)

    def scan_family_names(self):
        for block in self.data:
            if block.flags & UF2_FAMILY_ID_PRESENT:
                fam_id = block.reserved
                fam_name = self.get_family_name(fam_id)
                if fam_name not in self.families.keys():
                    # store address for this family
                    self.families[fam_name] = block.targetAddr
                else:
                    # store lowest address for this family
                    self.families[fam_name] = min(self.families[fam_name], block.targetAddr)

    def parse_output(
        self,
        output,
        qry,
    ) -> str:
        return match[1] if (match := re.search(qry, output)) else "42"

    def add_bin_info(self, uf2_file: Optional[Path] = None):
        # sourcery skip: extract-method
        # read the binary information using picotool and add the information to the class

        # supplied or previously read uf2 file
        uf2_file = uf2_file or self.file_path
        if not uf2_file:
            log.warning("No UF2 file loaded")
            return
        if "RP2040" in self.families.keys():
            # use picotool to read the binary information
            # shell=true allows same command for Linux & Windows
            picopath = Path(__file__).parent / "picotool"
            cmd = f"{picopath} info -a {uf2_file}"
            log.debug(f"Running {cmd}")
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    shell=True,
                )
            except OSError as e:
                log.error("picotool not found")
                log.exception(e)
                return
            if result.returncode == 0:
                # parse the output of picotool
                self.program_name = self.parse_output(result.stdout, r"\s+name:\s+(\w+)")
                self.board = self.parse_output(result.stdout, r"\s+pico_board:\s+(\w+)")
                # convert from hex_string to int
                self.binary_start = int(self.parse_output(result.stdout, r"binary start:\s+(0[xX][0-9a-fA-F]+)"), 16)
                self.binary_end = int(self.parse_output(result.stdout, r"binary end:\s+(0[xX][0-9a-fA-F]+)"), 16)
                self.drive_start = int(self.parse_output(result.stdout, r"embedded drive:\s+(0[xX][0-9a-fA-F]+)"), 16)
                self.drive_end = int(
                    self.parse_output(
                        result.stdout,
                        r"embedded drive:\s+0[xX][0-9a-fA-F]+-(0[xX][0-9a-fA-F]+)",
                    ),
                    16,
                )

    def add_binary(self, littlefs_img, *, chunk_size=0, start_addr: int = 0) -> "UF2File":
        """Read the contents of the littlefs_img file, create a new UF2File object, and iterate over the contents of the file in chunks of 256 bytes.
        For each chunk, create a new UF2Block object, set its properties, and append it to the UF2File object.
        Finally, set the numBlocks and blockNo properties of each block, and returns it.

        if the start address is not specified, the drive_start address is used

        chunk_size = must be between 255 - UF2_DATA_SIZE
        """
        if not chunk_size:
            chunk_size = UF2_DATA_SIZE
        assert chunk_size <= UF2_DATA_SIZE

        log.info(f"Reading littlefs binary image from {littlefs_img}")

        with open(littlefs_img, "rb") as f:
            littlefs_img = f.read()
        familyid = self.family_id
        start_addr = start_addr or self.drive_start

        bin_uf2 = UF2File()
        for i in range(0, len(littlefs_img), chunk_size):
            chunk = littlefs_img[i : i + chunk_size]
            block = UF2Block(chunk)
            block.flags = 0x0
            if familyid:
                block.flags |= 0x2000
                block.reserved = familyid
            block.targetAddr = start_addr + i
            block.payloadSize = len(chunk)
            bin_uf2.append(block)
        for i, block in enumerate(bin_uf2):
            block.numBlocks = len(bin_uf2)
            block.blockNo = i
        if bin_uf2:
            # add the littlefs image to the uf2 file
            log.debug(f"Extend uf2 with: {len(bin_uf2)} blocks")
            self.extend(bin_uf2)

        log.debug(f"LittleFS image size: {len(bin_uf2)} blocks")
        # return the newly converted uf2 file in case the caller needs that as well.
        return bin_uf2


def merge_uf2_littlefs(firmware_uf2: Path, littlefs_img: Path, out_path: Path, save_littlefs: bool = True, chunk_size=0):  # defaults to UF2_DATA_SIZE
    # Base file should be a firmware uf2 file
    base_uf2 = UF2File()
    base_uf2.read_uf2(firmware_uf2)
    base_uf2.add_bin_info()
    log.debug(base_uf2)

    littelfs_uf2 = None
    # read the littlefs image from build folder
    if littlefs_img and littlefs_img.exists():
        littelfs_uf2 = base_uf2.add_binary(littlefs_img, chunk_size=chunk_size)

    if littelfs_uf2 and save_littlefs:
        vfs_path = littlefs_img.with_suffix(".uf2")
        # write to file
        log.info(f"Writing {len(littelfs_uf2)} blocks to {vfs_path.name}")
        with open(vfs_path, "wb") as f:
            for block in littelfs_uf2:
                f.write(block)

    if out_path:
        base_uf2.scan()
        log.debug(f"Writing {len(base_uf2)} blocks to {out_path}")
        log.debug(base_uf2)  # print the new uf2 file

        with open(out_path, "wb") as f:
            for block in base_uf2:
                f.write(block)


def parse_args():
    parser = argparse.ArgumentParser(description="Tool to work with UF2 files")

    subparsers = parser.add_subparsers(dest="command")

    # Info subcommand
    info_parser = subparsers.add_parser("info", help="Show info on the UF2 file")
    info_parser.add_argument("base", type=str, help="Path to the UF2 file")

    # Merge subcommand
    merge_parser = subparsers.add_parser("merge", help="Merge a UF2 with a binary (littlefs) image")
    merge_parser.add_argument("base", type=str, help="Path to the firmware .UF2 file")
    merge_parser.add_argument("address", type=str, help="Memory address to store the littlefs image")
    merge_parser.add_argument("littlefs_img", type=str, help="Path to the a littlefs.img binary")
    merge_parser.add_argument("-o", "--out_path", type=str, help="Output file path")

    # Set info command as default
    parser.set_defaults(command="info")
    args = parser.parse_args()
    # read from environment or defaults
    args.base = Path(args.base)
    if args.command != "info":
        littlefs_img_path = os.environ.get(
            "littlefs_image",
            "build\\littlefs.img",
        )
        out_path = os.environ.get(
            "OUTPUT_PATH",
            "build\\firmware_lfs.uf2",
        )
        args.littlefs_img = Path(args.littlefs_img or littlefs_img_path)
        args.out_path = Path(args.out_path or out_path)

    # override defaults with command line arguments

    log.debug(args)
    return args


if __name__ == "__main__":
    # setup logging
    log.remove()
    log.add(sys.stderr, format="<level>{level:10}</level>| <cyan>{message}</cyan>", level="DEBUG")
    # commence
    args = parse_args()
    if args.command == "info":
        base_uf2 = UF2File()
        base_uf2.read_uf2(args.base)
        base_uf2.add_bin_info()
        print(f"UF2 file: {args.base}")
        print(base_uf2)

    elif args.command == "merge":
        merge_uf2_littlefs(firmware_uf2=args.base, littlefs_img=args.littlefs_img, out_path=args.out_path)

# done: rename to uf2_tool or similar.py
# done: add option to just show info on the uf2 file

# todo: low - append multiple UF2 files - and check for overlap in address space
# todo: Low - add  option to merge multiple uf2 or binary files
# todo: Low - remove dependency on picotool
