"""
network_sim.py - NetProbe Ağ Koşulu Simülatörü
Yapay paket kaybı ve gecikme ekler.
Deneylerde farklı kayıp oranlarını test etmek için kullanılır.

Kullanım:
    python network_sim.py --loss 0.1 --delay 0.05
    (bu komut %10 kayıp ve 50ms gecikme ile proxy başlatır)

Mimari:
    client → sim_proxy (bu dosya) → server
    client sim_port'a gönderir, proxy server_port'a iletir.
"""

import socket
import random
import time
import threading
import argparse


def start_proxy(
    listen_port : int   = 5000,   # client buraya gönderir
    server_host : str   = "127.0.0.1",
    server_port : int   = 5001,   # gerçek sunucu portu
    loss_rate   : float = 0.0,    # 0.0 - 1.0 arası kayıp oranı
    delay_s     : float = 0.0,    # saniye cinsinden sabit gecikme
    delay_jitter: float = 0.0,    # rastgele gecikme varyasyonu (saniye)
    verbose     : bool  = True,
):
    """
    UDP proxy. İstemciden gelen paketleri alır,
    loss_rate olasılığıyla düşürür, delay kadar bekler,
    sonra sunucuya iletir.
    ACK'ları sunucudan alıp istemciye geri yollar.
    """
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.bind(("0.0.0.0", listen_port))

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"\n🔀 Ağ Simülatörü Başlatıldı")
    print(f"   Dinleme portu : {listen_port}")
    print(f"   Sunucu        : {server_host}:{server_port}")
    print(f"   Kayıp oranı   : %{loss_rate * 100:.1f}")
    print(f"   Gecikme       : {delay_s*1000:.0f}ms ± {delay_jitter*1000:.0f}ms\n")

    dropped_count   = 0
    forwarded_count = 0
    client_addr_ref = [None]   # istemci adresini sakla (ACK dönüşü için)

    def forward_to_server():
        """İstemci → Sunucu yönü."""
        nonlocal dropped_count, forwarded_count
        while True:
            try:
                data, addr = client_sock.recvfrom(65535)
                client_addr_ref[0] = addr

                # Paket kaybı simülasyonu
                if random.random() < loss_rate:
                    dropped_count += 1
                    if verbose:
                        print(f"  ✗ [SIM DROP]  paket düşürüldü  (toplam drop: {dropped_count})")
                    continue

                # Gecikme simülasyonu
                actual_delay = delay_s + random.uniform(0, delay_jitter)
                if actual_delay > 0:
                    time.sleep(actual_delay)

                server_sock.sendto(data, (server_host, server_port))
                forwarded_count += 1
                if verbose:
                    print(f"  → [SIM FWD]   client→server  (iletilen: {forwarded_count})")

            except Exception as e:
                print(f"[SIM ERROR] forward_to_server: {e}")

    def forward_to_client():
        """Sunucu → İstemci yönü (ACK'lar)."""
        server_sock.bind(("0.0.0.0", listen_port + 100))  # geçici port
        while True:
            try:
                data, _ = server_sock.recvfrom(65535)
                if client_addr_ref[0]:
                    # ACK kaybı simülasyonu (isteğe bağlı, loss_rate/2)
                    if random.random() < loss_rate / 2:
                        if verbose:
                            print(f"  ✗ [SIM DROP]  ACK düşürüldü")
                        continue
                    client_sock.sendto(data, client_addr_ref[0])
                    if verbose:
                        print(f"  ← [SIM FWD]   server→client (ACK)")
            except Exception as e:
                print(f"[SIM ERROR] forward_to_client: {e}")

    # İki yönü ayrı thread'lerde çalıştır
    t1 = threading.Thread(target=forward_to_server, daemon=True)
    t2 = threading.Thread(target=forward_to_client, daemon=True)
    t1.start()
    t2.start()

    print("Çıkmak için Ctrl+C\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n📊 Simülatör istatistikleri:")
        print(f"   İletilen paket : {forwarded_count}")
        print(f"   Düşürülen paket: {dropped_count}")
        if forwarded_count + dropped_count > 0:
            actual_loss = dropped_count / (forwarded_count + dropped_count)
            print(f"   Gerçek kayıp   : %{actual_loss*100:.1f}")
        print("Simülatör kapatıldı.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetProbe Ağ Simülatörü")
    parser.add_argument("--listen-port",  default=5000, type=int,   help="İstemcinin bağlandığı port")
    parser.add_argument("--server-host",  default="127.0.0.1",      help="Gerçek sunucu IP")
    parser.add_argument("--server-port",  default=5001, type=int,   help="Gerçek sunucu portu")
    parser.add_argument("--loss",         default=0.0,  type=float, help="Paket kayıp oranı (0.0-1.0)")
    parser.add_argument("--delay",        default=0.0,  type=float, help="Sabit gecikme (saniye)")
    parser.add_argument("--jitter",       default=0.0,  type=float, help="Gecikme varyasyonu (saniye)")
    parser.add_argument("--quiet",        action="store_true",      help="Konsol çıktısını kapat")
    args = parser.parse_args()

    start_proxy(
        listen_port  = args.listen_port,
        server_host  = args.server_host,
        server_port  = args.server_port,
        loss_rate    = args.loss,
        delay_s      = args.delay,
        delay_jitter = args.jitter,
        verbose      = not args.quiet,
    )