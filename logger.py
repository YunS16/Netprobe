"""
logger.py - NetProbe Olay Kayıt Sistemi
"""

import csv
import time
import os

EVENT_SENT       = "SENT"
EVENT_ACK        = "ACK"
EVENT_TIMEOUT    = "TIMEOUT"
EVENT_RETRANSMIT = "RETRANSMIT"
EVENT_FAIL       = "FAIL"
EVENT_DUPLICATE  = "DUPLICATE"
EVENT_COMPLETE   = "COMPLETE"


class NetLogger:
    def __init__(self, log_file: str = "transfer.csv", verbose: bool = True):
        self.log_file       = log_file
        self.verbose        = verbose
        self.start_time     = time.time()
        self.sent_count     = 0
        self.ack_count      = 0
        self.timeout_count  = 0
        self.retransmit_count = 0
        self.fail_count     = 0
        self.duplicate_count = 0
        self.rtt_samples    = []

        os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else ".", exist_ok=True)
        with open(self.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "elapsed_ms", "event", "seq_num", "detail", "rtt_ms", "size_bytes"])

    def _elapsed_ms(self):
        return round((time.time() - self.start_time) * 1000, 2)

    def _write(self, event, seq_num=-1, detail="", rtt_ms="", size_bytes=""):
        with open(self.log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([round(time.time(), 4), self._elapsed_ms(), event, seq_num, detail, rtt_ms, size_bytes])

    def _print(self, msg):
        if self.verbose:
            print(msg)

    def log_sent(self, seq_num: int, size: int):
        self.sent_count += 1
        self._write(EVENT_SENT, seq_num, f"size={size}B", size_bytes=size)
        self._print(f"  → [SENT]       seq={seq_num:>5}  size={size}B")

    def log_ack(self, ack_num: int, rtt_s: float):
        self.ack_count += 1
        rtt_ms = round(rtt_s * 1000, 3)
        self.rtt_samples.append(rtt_ms)
        self._write(EVENT_ACK, ack_num, f"rtt={rtt_ms}ms", rtt_ms=rtt_ms)
        self._print(f"  ✓ [ACK]        ack={ack_num:>5}  rtt={rtt_ms}ms")

    def log_timeout(self, seq_num: int):
        self.timeout_count += 1
        self._write(EVENT_TIMEOUT, seq_num, "timeout")
        self._print(f"  ⏱ [TIMEOUT]    seq={seq_num:>5}")

    def log_retransmit(self, seq_num: int, attempt: int):
        self.retransmit_count += 1
        self._write(EVENT_RETRANSMIT, seq_num, f"attempt={attempt}")
        self._print(f"  ↩ [RETRANSMIT] seq={seq_num:>5}  attempt={attempt}")

    def log_fail(self, seq_num: int, max_retries: int):
        self.fail_count += 1
        self._write(EVENT_FAIL, seq_num, f"max_retries={max_retries} aşıldı")
        self._print(f"  ✗ [FAIL]       seq={seq_num:>5}  max_retries={max_retries} aşıldı")

    def log_duplicate(self, seq_num: int):
        self.duplicate_count += 1
        self._write(EVENT_DUPLICATE, seq_num, "duplicate paket yoksayıldı")
        self._print(f"  ⚠ [DUPLICATE]  seq={seq_num:>5}  yoksayıldı")

    def finalize(self, total_bytes: int, success: bool = True) -> dict:
        elapsed_s  = time.time() - self.start_time
        elapsed_ms = round(elapsed_s * 1000, 2)
        avg_rtt    = round(sum(self.rtt_samples) / len(self.rtt_samples), 3) if self.rtt_samples else 0
        throughput_kbps  = round((total_bytes * 8) / elapsed_s / 1000, 2) if elapsed_s > 0 else 0
        total_transmits  = self.sent_count + self.retransmit_count
        goodput_ratio    = round(self.ack_count / total_transmits, 4) if total_transmits > 0 else 0
        retransmit_rate  = round(self.retransmit_count / self.sent_count, 4) if self.sent_count > 0 else 0

        stats = {
            "status"           : "BAŞARILI" if success else "BAŞARISIZ",
            "elapsed_ms"       : elapsed_ms,
            "total_bytes"      : total_bytes,
            "sent"             : self.sent_count,
            "acks"             : self.ack_count,
            "timeouts"         : self.timeout_count,
            "retransmits"      : self.retransmit_count,
            "fails"            : self.fail_count,
            "duplicates"       : self.duplicate_count,
            "avg_rtt_ms"       : avg_rtt,
            "throughput_kbps"  : throughput_kbps,
            "goodput_ratio"    : goodput_ratio,
            "retransmit_rate"  : retransmit_rate,
        }

        self._write(EVENT_COMPLETE, detail=str(stats))
        self._print("\n" + "="*50)
        self._print(f"  AKTARIM {stats['status']}")
        self._print(f"  Toplam süre      : {elapsed_ms} ms")
        self._print(f"  Toplam veri      : {total_bytes} byte")
        self._print(f"  Gönderilen paket : {self.sent_count}")
        self._print(f"  Alınan ACK       : {self.ack_count}")
        self._print(f"  Timeout          : {self.timeout_count}")
        self._print(f"  Retransmit       : {self.retransmit_count}")
        self._print(f"  Başarısız paket  : {self.fail_count}")
        self._print(f"  Ortalama RTT     : {avg_rtt} ms")
        self._print(f"  Throughput       : {throughput_kbps} kbps")
        self._print(f"  Goodput oranı    : {goodput_ratio}")
        self._print(f"  Retransmit oranı : {retransmit_rate}")
        self._print("="*50 + "\n")

        return stats