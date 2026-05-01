"""
client.py - NetProbe UDP İstemci
Sliding Window protokolü ile dosyayı sunucuya gönderir.
"""

import socket
import hashlib
import os
import time
import threading
import argparse
from packet import build_data_packet, parse_ack_packet, split_file
from logger import NetLogger

# Varsayılan ayarlar
DEFAULT_HOST        = "127.0.0.1"
DEFAULT_PORT        = 5001
DEFAULT_CHUNK_SIZE  = 1024   # byte
DEFAULT_WINDOW_SIZE = 4      # aynı anda uçuşta olabilecek paket sayısı
DEFAULT_TIMEOUT     = 1.0    # saniye
DEFAULT_MAX_RETRY   = 5


def send_file(
    filepath    : str,
    host        : str   = DEFAULT_HOST,
    port        : int   = DEFAULT_PORT,
    chunk_size  : int   = DEFAULT_CHUNK_SIZE,
    window_size : int   = DEFAULT_WINDOW_SIZE,
    timeout     : float = DEFAULT_TIMEOUT,
    max_retry   : int   = DEFAULT_MAX_RETRY,
    loss_rate   : float = 0.0,   # network_sim entegrasyonu için
    log_file    : str   = "logs/client.csv",
    verbose     : bool  = True,
):
    logger = NetLogger(log_file=log_file, verbose=verbose)

    # Dosyayı parçalara böl
    chunks = split_file(filepath, chunk_size)
    filename = os.path.basename(filepath)
    total_packets = len(chunks) + 1   # +1 META paketi için
    total_bytes = os.path.getsize(filepath)

    print(f"\n📤 Gönderiliyor : {filename}")
    print(f"   Boyut        : {total_bytes} byte")
    print(f"   Paket sayısı : {len(chunks)}")
    print(f"   Paket boyutu : {chunk_size} byte")
    print(f"   Window size  : {window_size}")
    print(f"   Timeout      : {timeout}s")
    print(f"   Max retry    : {max_retry}\n")

    # MD5 hesapla (bütünlük doğrulama için)
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        md5.update(f.read())
    file_hash = md5.hexdigest()
    print(f"🔑 MD5 (gönderen): {file_hash}\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    server = (host, port)

    # ── META paketi gönder (seq=0) ──
    meta_payload = f"META:{filename}".encode()
    meta_pkt = build_data_packet(seq_num=0, total_packets=total_packets, payload=meta_payload)
    for _ in range(max_retry):
        sock.sendto(meta_pkt, server)
        try:
            raw, _ = sock.recvfrom(65535)
            ack = parse_ack_packet(raw)
            if ack and ack["ack_num"] == 0:
                break
        except (socket.timeout, ConnectionResetError):
            continue
    else:
        print("✗ META paketi gönderilemedi, aktarım iptal.")
        sock.close()
        return False

    # ── Sliding Window ──
    base        = 0              # onaylanmamış en küçük seq (chunk index)
    next_seq    = 0              # gönderilecek bir sonraki seq
    n           = len(chunks)
    send_times  = {}             # seq -> gönderim zamanı
    retry_count = {}             # seq -> deneme sayısı
    failed_pkts = []             # başarısız paketler
    lock        = threading.Lock()
    all_acked   = threading.Event()

    def receiver_thread():
        """Arka planda ACK dinler."""
        nonlocal base
        while not all_acked.is_set():
            try:
                raw, _ = sock.recvfrom(65535)
                ack = parse_ack_packet(raw)
                if ack is None:
                    continue
                ack_num = ack["ack_num"] - 1   # chunk index'e çevir (seq 1'den başlıyor)
                with lock:
                    if ack_num in send_times:
                        rtt = time.time() - send_times.pop(ack_num)
                        logger.log_ack(ack_num, rtt)
                        if ack_num >= base:
                            base = ack_num + 1
                        if base >= n:
                            all_acked.set()
            except (socket.timeout, ConnectionResetError):
                continue
            except Exception:
                continue

    recv_thread = threading.Thread(target=receiver_thread, daemon=True)
    recv_thread.start()

    # Ana gönderim döngüsü
    while base < n and len(failed_pkts) == 0:
        with lock:
            # Window dolmadıysa yeni paket gönder
            while next_seq < n and next_seq < base + window_size:
                seq_num  = next_seq + 1   # seq 1'den başlıyor (0 META)
                payload  = chunks[next_seq]
                pkt      = build_data_packet(seq_num, total_packets, payload)
                sock.sendto(pkt, server)
                send_times[next_seq]  = time.time()
                retry_count[next_seq] = 0
                logger.log_sent(seq_num, len(payload))
                next_seq += 1

        time.sleep(0.001)

        # Timeout kontrolü
        now = time.time()
        with lock:
            for seq_idx in list(send_times.keys()):
                if now - send_times[seq_idx] > timeout:
                    if retry_count[seq_idx] >= max_retry:
                        logger.log_fail(seq_idx + 1, max_retry)
                        failed_pkts.append(seq_idx)
                        send_times.pop(seq_idx)
                    else:
                        # Yeniden gönder
                        retry_count[seq_idx] += 1
                        logger.log_timeout(seq_idx + 1)
                        logger.log_retransmit(seq_idx + 1, retry_count[seq_idx])
                        seq_num = seq_idx + 1
                        payload = chunks[seq_idx]
                        pkt     = build_data_packet(seq_num, total_packets, payload)
                        sock.sendto(pkt, server)
                        send_times[seq_idx] = time.time()

    # Tüm ACK'lar gelene kadar bekle
    all_acked.wait(timeout=timeout * max_retry)
    sock.close()

    success = len(failed_pkts) == 0
    stats = logger.finalize(total_bytes=total_bytes, success=success)

    if failed_pkts:
        print(f"⚠ Başarısız paketler: {[p+1 for p in failed_pkts]}")

    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetProbe UDP İstemci")
    parser.add_argument("filepath",                                   help="Gönderilecek dosya")
    parser.add_argument("--host",        default=DEFAULT_HOST,        help="Sunucu IP")
    parser.add_argument("--port",        default=DEFAULT_PORT,        type=int)
    parser.add_argument("--chunk-size",  default=DEFAULT_CHUNK_SIZE,  type=int, help="Paket boyutu (byte)")
    parser.add_argument("--window-size", default=DEFAULT_WINDOW_SIZE, type=int, help="Sliding window boyutu")
    parser.add_argument("--timeout",     default=DEFAULT_TIMEOUT,     type=float, help="Timeout süresi (s)")
    parser.add_argument("--max-retry",   default=DEFAULT_MAX_RETRY,   type=int, help="Maks yeniden deneme")
    parser.add_argument("--log-file",    default="logs/client.csv",   help="Log dosyası yolu")
    parser.add_argument("--quiet",       action="store_true",         help="Konsol çıktısını kapat")
    args = parser.parse_args()

    send_file(
        filepath    = args.filepath,
        host        = args.host,
        port        = args.port,
        chunk_size  = args.chunk_size,
        window_size = args.window_size,
        timeout     = args.timeout,
        max_retry   = args.max_retry,
        log_file    = args.log_file,
        verbose     = not args.quiet,
    )