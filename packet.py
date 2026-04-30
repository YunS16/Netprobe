"""
packet.py - NetProbe Paket Yapısı
"""

import struct
import zlib

TYPE_DATA = 0x01
TYPE_ACK  = 0x02

DATA_HEADER_SIZE = struct.calcsize("!B I I H I")   # 15 byte
ACK_PACKET_SIZE  = struct.calcsize("!B I I")        # 9 byte


def compute_checksum(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def build_data_packet(seq_num: int, total_packets: int, payload: bytes) -> bytes:
    payload_len = len(payload)
    header_no_checksum = struct.pack("!B I I H I", TYPE_DATA, seq_num, total_packets, payload_len, 0)
    checksum = compute_checksum(header_no_checksum + payload)
    header = struct.pack("!B I I H I", TYPE_DATA, seq_num, total_packets, payload_len, checksum)
    return header + payload


def parse_data_packet(raw: bytes) -> dict | None:
    if len(raw) < DATA_HEADER_SIZE:
        return None
    try:
        pkt_type, seq_num, total_packets, payload_len, checksum = struct.unpack("!B I I H I", raw[:DATA_HEADER_SIZE])
    except struct.error:
        return None
    if pkt_type != TYPE_DATA:
        return None
    payload = raw[DATA_HEADER_SIZE:DATA_HEADER_SIZE + payload_len]
    header_no_checksum = struct.pack("!B I I H I", TYPE_DATA, seq_num, total_packets, payload_len, 0)
    if compute_checksum(header_no_checksum + payload) != checksum:
        return None
    return {"type": pkt_type, "seq_num": seq_num, "total_packets": total_packets,
            "payload_len": payload_len, "checksum": checksum, "payload": payload}


def build_ack_packet(ack_num: int) -> bytes:
    body = struct.pack("!B I", TYPE_ACK, ack_num)
    checksum = compute_checksum(body)
    return struct.pack("!B I I", TYPE_ACK, ack_num, checksum)


def parse_ack_packet(raw: bytes) -> dict | None:
    if len(raw) < ACK_PACKET_SIZE:
        return None
    try:
        pkt_type, ack_num, checksum = struct.unpack("!B I I", raw[:ACK_PACKET_SIZE])
    except struct.error:
        return None
    if pkt_type != TYPE_ACK:
        return None
    body = struct.pack("!B I", TYPE_ACK, ack_num)
    if compute_checksum(body) != checksum:
        return None
    return {"type": pkt_type, "ack_num": ack_num, "checksum": checksum}


def split_file(filepath: str, chunk_size: int) -> list[bytes]:
    chunks = []
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
    return chunks