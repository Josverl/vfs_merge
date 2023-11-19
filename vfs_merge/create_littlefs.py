#!/usr/bin/python3
import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from littlefs import LittleFS
from loguru import logger as log

from .portboard_disk import (VFLASH_BLOCK_SIZE, VFS_LFS1, VFS_LFS2,
                             port_info_list)


def folder_to_lfs(
    source: str,
    block_size,
    block_count,
    prog_size=256,
    disk_version: int = VFS_LFS2,
    target: str = "build/littlefs.img",
):
    """
    Create Little FS image with the contents of the folder.

    Parameters:
    - folder: source folder to wrap
    - image: destination image file
    - disk_version: LittleFS File System Version 0x0002_0000 needed by micropython builds @v1.20.0
    """
    log.debug(f"Create new filesystem with: {block_count} blocks of {block_size} bytes = {int(block_count*block_size/1024)}Kb")
    fs = LittleFS(
        block_size=block_size,
        block_count=block_count,
        prog_size=prog_size,
        disk_version=disk_version,
    )
    source_path = Path(source)
    log.info(f"Add files from {source_path}")
    for filename in source_path.rglob("*"):
        lfs_fname = f"/{filename.relative_to(source_path).as_posix()}"
        if filename.is_file():
            with open(filename, "rb") as src_file:
                # use the relative path to source as the littlefs filename
                log.debug(f"Adding {lfs_fname}")
                with fs.open(lfs_fname, "wb") as lfs_file:
                    lfs_file.write(src_file.read())
        elif filename.is_dir():
            fs.mkdir(lfs_fname)
    # verify

    log.debug(f"write filesystem to {target}")
    with open(target, "wb") as fh:
        fh.write(fs.context.buffer)
    return True


#


def main(port_name: str):
    port_info = next((p for p in port_info_list if p.name.lower() == port_name.lower()), None)
    if not port_info:
        log.error(f"Port {port_name} not found")
        return

    page_size = port_info.page_size
    block_size = port_info.block_size
    block_count = port_info.block_count
    image_size = port_info.image_size
    log.debug(f"Port: {port_name}, PageSize: {page_size}, BlockSize: {block_size}, BlockCount: {block_count}, ImageSize: {int(image_size/1024)}Kb")

    # location of workspace
    workspace_dir = Path(__file__).parent.parent.absolute()

    # where are artefacts compared to workspace
    build_pth = workspace_dir / "build"
    build_pth.mkdir(parents=True, exist_ok=True)
    littlefs_image = build_pth / "littlefs.img"
    # create littlefs
    folder_to_lfs(
        source=f"{workspace_dir}/src",
        target=str(littlefs_image),
        disk_version=VFS_LFS2,
        block_size=block_size,
        block_count=block_count,
        prog_size=page_size,
    )


if __name__ == "__main__":
    # setup logging
    log.remove()
    log.add(sys.stderr, format="<level>{level:10}</level>| <cyan>{message}</cyan>", level="DEBUG")
    # go
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", "--port-board", help="the name of the port and board to build for (rp2-pico, esp32-generic)")
    args = parser.parse_args()
    port = args.port or os.environ.get("PORTBOARD") or "esp32-generic"
    main(port)
