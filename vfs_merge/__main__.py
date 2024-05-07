import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger as log

from .create_littlefs import folder_to_lfs
from .portboard_disk import port_info_list
from .uf2_tool import merge_uf2_littlefs


def get_disk_info(port: str):  # sourcery skip: use-next
    """Return the disk info for the given port name."""
    for port_info in port_info_list:
        if port_info.name == port:
            return port_info
    port = f"{port}-generic"
    for port_info in port_info_list:
        if port_info.name == port:
            return port_info
    return None


def esptool_merge(output_bin: Path, firmware_bin: Path, littlefs_img: Path, littlefs_address=0x200000, flash_size="4MB"):
    """\
    Merge the firmware and littlefs image into a single binary.
    
    The merge_bin command will merge multiple binary files (of any kind) into a single file that can be flashed to a device later.
    Any gaps between the input files are padded with 0xFF bytes

    https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/basic-commands.html?highlight=merge_bin#merge-binaries-for-flashing-merge-bin
    """
    log.info(f"Merge firmware and littlefs image into {output_bin}")
    command = [
        "esptool",
        "--chip",
        "esp32",
        "merge_bin",
        "-o",
        str(output_bin),
        "--flash_mode",
        "dio",
        "--flash_size",
        flash_size,
        "0x1000",
        str(firmware_bin),
        f"0x{littlefs_address:08x}",
        str(littlefs_img),
    ]
    log.debug("running: " + " ".join(command))
    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log.exception(e)
        return False


def firmware_port(port: str, firmware_path: Path):
    if port == "auto":
        port = firmware_path.stem.split("-")[0] or "-"
        if port.endswith("spiram"):
            port = port[:-6]
    ver = firmware_path.stem.split("-")[-1] or "-"

    return port


def main(source_path: Path, firmware_path: Path, port: str, build_path: Path):
    # get information on the port and firmware as that is needed to size the littlefs image correctly

    port = firmware_port(port, firmware_path)

    log.info(f"Micropython Port: {port}")
    log.info(f"Source folder path: {source_path}")
    log.info(f"Firmware path: {firmware_path}")
    log.info(f"Build path: {build_path}")

    disk_info = get_disk_info(port)
    if not disk_info:
        log.error(f"Port {port} not found")
        return
    # create littlefs image for this port
    littlefs_image = build_path / "littlefs.img"
    log.info(f"Create littlefs image: {littlefs_image}")

    try:
        folder_to_lfs(
            source=str(source_path),
            target=str(littlefs_image),
            disk_version=disk_info.vfstype,
            block_size=disk_info.block_size,
            block_count=disk_info.block_count,
        )
    except Exception as e:
        log.exception(e)
        return
    # now merge the firmware and littlefs image into a single binary
    # this is different for each finary format
    if port.startswith("esp32"):
        esptool_merge(
            firmware_bin=firmware_path,
            littlefs_img=littlefs_image,
            output_bin=build_path / "firmware_lfs.bin",
            littlefs_address=disk_info.start_address,
        )
    elif port.startswith("rp2"):
        merge_uf2_littlefs(
            firmware_uf2=firmware_path,
            littlefs_img=littlefs_image,
            out_path=build_path / "firmware_lfs.uf2",
            save_littlefs=True,
            chunk_size=256,
        )


def parse_cmdline():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Merge source code and firmware into a single file.")
    parser.add_argument("--port", "--portboard", "-p", type=str, help="MicroPython port[-board]", default=os.environ.get("PORTBOARD", "auto"))
    parser.add_argument("--source", "-s", type=str, help="source folder path ", default=os.environ.get("SRC", "./src"))
    parser.add_argument("--firmware", "-f", type=str, help="firmware path", default=os.environ.get("FIRMWARE", "./firmware"))
    parser.add_argument("--build", "-B", type=str, help="build folder", default=os.environ.get("BUILD", "./build"))

    args = parser.parse_args()
    args.source = Path(args.source)
    args.build = Path(args.build)
    args.firmware = Path(args.firmware)
    # firmware should be a folder or file name
    if not args.firmware.exists():
        # TODO , support * in file name
        log.error(f"firmware path {args.firmware} does not exist")
        sys.exit(1)

    if args.firmware.is_dir():
        prefix = args.port if args.port != "auto" else ""
        # get most recent file matching prefix
        # todo: this is not very robust as it depends on the file name format of the firmware
        # esp32-20230426-v1.20.0.bin ~~ <port>-20*
        firmware_files = list(args.firmware.glob(f"{prefix}*-20*"))
        if not firmware_files:
            log.error(f"No firmware found for port '{args.port}' in {args.firmware}")
            sys.exit(1)
        firmware_file = max(firmware_files, key=lambda f: f.stat().st_mtime)
        args.firmware = firmware_file

    return args

def cli():
    # setup logging
    log.remove()
    log.add(sys.stderr, format="<level>{level:10}</level>| <cyan>{message}</cyan>", level="DEBUG")
    # go
    args = parse_cmdline()
    main(args.source, args.firmware, args.port, args.build)

if __name__ == "__main__":
    cli()

# TODO: test on linux
# TODO: use rich-click
# TODO: add --verbose option to control logging
# Low PRIO
# todo: test with rp2* ports that are not in the list
# todo: add support for esp32-s2 and other boards
# todo: add support for FAT filesystems
# https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/storage/fatfsgen.html?highlight=checksum#fatfsgen-py
