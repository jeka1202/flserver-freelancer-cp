from __future__ import annotations

import argparse
import struct
from pathlib import Path


ENTRY_SIZE = 44
NODE_FOLDER = 0x10
NODE_DATA = 0x80


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_c_string(blob: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(blob):
        return ""
    end = blob.find(b"\x00", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("latin1", errors="replace")


def parse_utf_nodes(data: bytes) -> tuple[list[dict], int]:
    if data[:4] != b"UTF ":
        raise ValueError("not a Freelancer UTF/3DB file")

    tree_offset = read_u32(data, 0x08)
    tree_size = read_u32(data, 0x0C)
    entry_size = read_u32(data, 0x14)
    string_offset = read_u32(data, 0x18)
    string_size = read_u32(data, 0x1C)
    data_start = read_u32(data, 0x24)

    if entry_size != ENTRY_SIZE:
        raise ValueError(f"unexpected UTF entry size: {entry_size}")

    string_table = data[string_offset:string_offset + string_size]
    count = tree_size // entry_size

    nodes: list[dict] = []

    for index in range(count):
        offset = tree_offset + index * entry_size
        values = struct.unpack_from("<11I", data, offset)

        # Freelancer UTF node layout, as used in .3db:
        # 0: sibling/next offset inside tree, 1: name offset in string table,
        # 2: flags/type, 4: child offset or data offset,
        # 5/6/7: size fields for data nodes.
        name = read_c_string(string_table, values[1])

        nodes.append({
            "index": index,
            "name": name,
            "flags": values[2],
            "child_or_data_offset": values[4],
            "size": values[5],
            "allocated_size": values[6],
            "uncompressed_size": values[7],
            "raw": values,
        })

    return nodes, data_start


def extract_tga_from_3db(path: Path, output_dir: Path, overwrite: bool = True) -> list[Path]:
    data = path.read_bytes()
    nodes, data_start = parse_utf_nodes(data)

    output_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    current_tga_name = ""

    for node in nodes:
        name = node["name"]

        if name.lower().endswith(".tga"):
            current_tga_name = Path(name).name

        if name.upper() == "MIP0" and node["flags"] == NODE_DATA:
            start = data_start + int(node["child_or_data_offset"])
            size = int(node["size"])
            blob = data[start:start + size]

            # В твоих Freelancer .3db MIP0 уже содержит полноценный TGA:
            # 00 00 02 ... width height bpp ...
            if len(blob) < 18:
                continue

            if blob[2] not in (2, 10):  # uncompressed or RLE true-color TGA
                continue

            tga_name = current_tga_name or (path.stem + ".tga")
            out_path = output_dir / tga_name

            if out_path.exists() and not overwrite:
                extracted.append(out_path)
                continue

            out_path.write_bytes(blob)
            extracted.append(out_path)

    return extracted


def convert_to_png(tga_files: list[Path], png_dir: Path, delete_tga: bool = False) -> list[Path]:
    try:
        from PIL import Image
    except Exception:
        print("Pillow не установлен, PNG-конвертация пропущена.")
        print("Установить можно так: py -m pip install pillow")
        return []

    png_dir.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []

    for tga in tga_files:
        png = png_dir / (tga.stem + ".png")
        try:
            with Image.open(tga) as img:
                img.save(png)
            converted.append(png)
            if delete_tga:
                tga.unlink(missing_ok=True)
        except Exception as exc:
            print(f"[WARN] Не удалось конвертировать {tga}: {exc}")

    return converted


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract embedded TGA textures from Freelancer .3db UTF files")
    parser.add_argument("--models", required=True, help="Папка с .3db или один .3db файл")
    parser.add_argument("--out", default="extracted_tga", help="Куда сохранять TGA")
    parser.add_argument("--png", default="", help="Если указано, дополнительно конвертировать TGA в PNG в эту папку")
    parser.add_argument("--delete-tga", action="store_true", help="После PNG-конвертации удалить временные TGA")
    parser.add_argument("--no-overwrite", action="store_true", help="Не перезаписывать существующие TGA")
    args = parser.parse_args()

    source = Path(args.models)
    out_dir = Path(args.out)

    if source.is_file():
        files = [source]
    else:
        files = sorted(source.rglob("*.3db"))

    if not files:
        raise SystemExit("Файлы .3db не найдены.")

    all_tga: list[Path] = []

    for file in files:
        try:
            extracted = extract_tga_from_3db(file, out_dir, overwrite=not args.no_overwrite)
            if extracted:
                print(f"[OK] {file.name}: {', '.join(p.name for p in extracted)}")
                all_tga.extend(extracted)
            else:
                print(f"[--] {file.name}: TGA/MIP0 не найден")
        except Exception as exc:
            print(f"[ERR] {file}: {exc}")

    print()
    print(f"TGA extracted: {len(all_tga)}")

    if args.png:
        png_files = convert_to_png(all_tga, Path(args.png), delete_tga=args.delete_tga)
        print(f"PNG converted: {len(png_files)}")


if __name__ == "__main__":
    main()
