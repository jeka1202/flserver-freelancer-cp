from __future__ import annotations

LOGICAL_BITS = 30
PHYSICAL_BITS = 32
FL_HASH_POLYNOMIAL = 0xA001 << (LOGICAL_BITS - 16)


def make_crc_table(polynomial: int) -> list[int]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            if value & 1:
                value = (value >> 1) ^ polynomial
            else:
                value >>= 1
            value &= 0xFFFFFFFF
        table.append(value)
    return table


CRC_TABLE = make_crc_table(FL_HASH_POLYNOMIAL)


def raw_fl_hash(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value >> 8) ^ CRC_TABLE[(value ^ byte) & 0xFF]
    return ((value >> 24) | ((value >> 8) & 0x0000FF00) | ((value << 8) & 0x00FF0000) | (value << 24)) & 0xFFFFFFFF


def nickname_hash(nickname: str) -> str:
    value = (raw_fl_hash(nickname.lower().encode()) >> (PHYSICAL_BITS - LOGICAL_BITS)) | 0x80000000
    return str(value)
