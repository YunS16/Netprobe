"""
server.py - NetProbe UDP Sunucu
Dosyayı istemciden alır, yeniden birleştirir, bütünlüğü doğrular.
"""

import socket
import hashlib
import os
import time
import argparse
from packet import parse_data_packet, build_ack_packet
from logger import NetLogger


def receive_file(
    host: str       = "0.0.0.0",
    port: int       = 5001,
    output_dir: str = "received",
    log_file: str   = "logs/server.csv",
    verbose: bool   = True,
):
    os.makedirs(output_dir, exist_ok=True)
    logger = NetLogger(log_file=log_file, verbose=verbose)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"\n🟢 Sunucu başlatıldı → {host}:{port}  (bekleniyor...)\n")

    # İlk paketi al → dosya adı ve toplam paket sayısı öğrenilir
    received_chunks = {}   # seq_num -> payload
    total_packets   = None
    client_addr     = None
    filename        = "received_file"
    total_bytes     = 0

    while True:
        try:
            raw, addr = sock.recvfrom(65535)
        except KeyboardInterrupt:
            print("\nSunucu kapatıldı.")
            break

        pkt = parse_data_packet(raw)

        # Geçersiz / bozuk paket → yoksay
        if pkt is None:
            continue

        client_addr   = addr
        seq_num       = pkt["seq_num"]
        total_packets = pkt["total_packets"]
        payload       = pkt["payload"]

        # İlk pakette dosya adı payload'ın başında gelir (META paketi)
        # seq_num == 0 ve payload "FILENAME:<ad>" formatındaysa meta pakettir
        if seq_num == 0 and payload.startswith(b"META:"):
            filename = payload[5:].decode(errors="replace")
            print(f"📁 Dosya adı: {filename}  |  Toplam paket: {total_packets}")
            ack = build_ack_packet(0)
            sock.sendto(ack, client_addr)
            continue

        # Duplicate paket kontrolü
        if seq_num in received_chunks:
            logger.log_duplicate(seq_num)
            ack = build_ack_packet(seq_num)
            sock.sendto(ack, client_addr)
            continue

        # Yeni paket → kaydet
        received_chunks[seq_num] = payload
        total_bytes += len(payload)
        logger.log_sent(seq_num, len(payload))   # sunucu tarafında "alındı" anlamında

        # ACK gönder
        ack = build_ack_packet(seq_num)
        sock.sendto(ack, client_addr)

        # Tüm paketler geldi mi?
        if total_packets and len(received_chunks) >= total_packets - 1:
            # seq 0 META paketi, gerçek veri 1'den başlıyor
            break

    sock.close()

    # Dosyayı yeniden birleştir
    out_path = os.path.join(output_dir, os.path.basename(filename))
    with open(out_path, "wb") as f:
        for i in sorted(received_chunks.keys()):
            f.write(received_chunks[i])

    # MD5 hash doğrulama
    md5 = hashlib.md5()
    with open(out_path, "rb") as f:
        md5.update(f.read())
    file_hash = md5.hexdigest()

    print(f"\n✅ Dosya kaydedildi : {out_path}")
    print(f"🔑 MD5 hash        : {file_hash}")

    logger.finalize(total_bytes=total_bytes, success=True)
    return out_path, file_hash


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetProbe UDP Sunucu")
    parser.add_argument("--host",       default="0.0.0.0",        help="Dinlenecek IP")
    parser.add_argument("--port",       default=5001, type=int,    help="Dinlenecek port")
    parser.add_argument("--output-dir", default="received",        help="Alınan dosyaların kaydedileceği klasör")
    parser.add_argument("--log-file",   default="logs/server.csv", help="Log dosyası yolu")
    parser.add_argument("--quiet",      action="store_true",       help="Konsol çıktısını kapat")
    args = parser.parse_args()

    receive_file(
        host       = args.host,
        port       = args.port,
        output_dir = args.output_dir,
        log_file   = args.log_file,
        verbose    = not args.quiet,
    )