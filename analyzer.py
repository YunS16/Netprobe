"""
analyzer.py - NetProbe Performans Analiz ve Grafik Üretimi
Log CSV dosyalarını okur, metrikleri hesaplar, grafikleri kaydeder.

Kullanım:
    python analyzer.py --log logs/client.csv --output graphs/
"""

import csv
import os
import argparse
import json
from collections import defaultdict

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB = True
except ImportError:
    MATPLOTLIB = False
    print("⚠ matplotlib bulunamadı. Grafikler üretilmeyecek.")
    print("  Kurmak için: pip install matplotlib\n")


# ──────────────────────────────────────────────
#  CSV Okuma
# ──────────────────────────────────────────────

def load_log(log_file: str) -> list[dict]:
    """CSV log dosyasını okur, satırları dict listesi olarak döndürür."""
    rows = []
    with open(log_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ──────────────────────────────────────────────
#  Metrik Hesaplama
# ──────────────────────────────────────────────

def compute_metrics(rows: list[dict]) -> dict:
    """Log satırlarından performans metriklerini hesaplar."""
    sent       = [r for r in rows if r["event"] == "SENT"]
    acks       = [r for r in rows if r["event"] == "ACK"]
    timeouts   = [r for r in rows if r["event"] == "TIMEOUT"]
    retrans    = [r for r in rows if r["event"] == "RETRANSMIT"]
    fails      = [r for r in rows if r["event"] == "FAIL"]
    complete   = [r for r in rows if r["event"] == "COMPLETE"]

    rtt_values = []
    for r in acks:
        try:
            rtt_values.append(float(r["rtt_ms"]))
        except (ValueError, KeyError):
            pass

    total_bytes = 0
    for r in sent:
        try:
            total_bytes += int(r["size_bytes"])
        except (ValueError, KeyError):
            pass

    elapsed_ms = 0
    if complete:
        detail = complete[-1]["detail"]
        # elapsed_ms değerini detail string'inden çek
        for part in detail.split("|"):
            if "elapsed_ms" in part:
                try:
                    elapsed_ms = float(part.split("=")[1].replace("}", "").replace("'", "").strip())
                except:
                    pass

    elapsed_s = elapsed_ms / 1000 if elapsed_ms > 0 else 1

    throughput_kbps = round((total_bytes * 8) / elapsed_s / 1000, 2)
    total_transmits = len(sent) + len(retrans)
    goodput_ratio   = round(len(acks) / total_transmits, 4) if total_transmits > 0 else 0
    retrans_rate    = round(len(retrans) / len(sent), 4) if sent else 0
    avg_rtt         = round(sum(rtt_values) / len(rtt_values), 3) if rtt_values else 0
    loss_rate       = round(len(fails) / len(sent), 4) if sent else 0

    return {
        "sent_count"      : len(sent),
        "ack_count"       : len(acks),
        "timeout_count"   : len(timeouts),
        "retrans_count"   : len(retrans),
        "fail_count"      : len(fails),
        "total_bytes"     : total_bytes,
        "elapsed_ms"      : elapsed_ms,
        "throughput_kbps" : throughput_kbps,
        "goodput_ratio"   : goodput_ratio,
        "retrans_rate"    : retrans_rate,
        "avg_rtt_ms"      : avg_rtt,
        "loss_rate"       : loss_rate,
        "rtt_values"      : rtt_values,
    }


# ──────────────────────────────────────────────
#  Grafikler
# ──────────────────────────────────────────────

def plot_rtt_over_time(rows: list[dict], output_dir: str):
    """ACK alım zamanına göre RTT değişimi grafiği."""
    acks = [r for r in rows if r["event"] == "ACK"]
    if not acks:
        return

    elapsed = []
    rtt     = []
    for r in acks:
        try:
            elapsed.append(float(r["elapsed_ms"]))
            rtt.append(float(r["rtt_ms"]))
        except (ValueError, KeyError):
            pass

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(elapsed, rtt, color="#2196F3", linewidth=1.2, label="RTT (ms)")
    ax.axhline(sum(rtt)/len(rtt), color="#FF5722", linestyle="--", linewidth=1, label=f"Ort. RTT: {sum(rtt)/len(rtt):.2f}ms")
    ax.set_xlabel("Geçen Süre (ms)")
    ax.set_ylabel("RTT (ms)")
    ax.set_title("RTT Zaman Grafiği")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "rtt_over_time.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  📊 {path}")


def plot_event_timeline(rows: list[dict], output_dir: str):
    """Olayların zaman çizelgesi (SENT, ACK, TIMEOUT, RETRANSMIT)."""
    colors = {
        "SENT"       : "#4CAF50",
        "ACK"        : "#2196F3",
        "TIMEOUT"    : "#FF9800",
        "RETRANSMIT" : "#F44336",
        "FAIL"       : "#9C27B0",
        "DUPLICATE"  : "#795548",
    }

    fig, ax = plt.subplots(figsize=(12, 5))

    for r in rows:
        event = r["event"]
        if event not in colors:
            continue
        try:
            x = float(r["elapsed_ms"])
            y = list(colors.keys()).index(event)
            ax.scatter(x, y, color=colors[event], s=15, alpha=0.7)
        except (ValueError, KeyError):
            pass

    ax.set_yticks(range(len(colors)))
    ax.set_yticklabels(list(colors.keys()))
    ax.set_xlabel("Geçen Süre (ms)")
    ax.set_title("Olay Zaman Çizelgesi")
    ax.grid(True, alpha=0.2)

    patches = [mpatches.Patch(color=c, label=e) for e, c in colors.items()]
    ax.legend(handles=patches, loc="upper right", fontsize=8)
    plt.tight_layout()
    path = os.path.join(output_dir, "event_timeline.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  📊 {path}")


def plot_metrics_bar(metrics: dict, output_dir: str):
    """Throughput, Goodput oranı ve Retransmission oranı bar grafiği."""
    labels = ["Throughput\n(kbps)", "Goodput\nOranı", "Retransmit\nOranı", "Kayıp\nOranı"]
    values = [
        metrics["throughput_kbps"],
        metrics["goodput_ratio"] * 100,
        metrics["retrans_rate"]  * 100,
        metrics["loss_rate"]     * 100,
    ]
    bar_colors = ["#2196F3", "#4CAF50", "#FF9800", "#F44336"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=bar_colors, edgecolor="white", width=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{val:.2f}", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Değer")
    ax.set_title("Performans Metrikleri Özeti")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "metrics_bar.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  📊 {path}")


def plot_retransmit_heatmap(rows: list[dict], output_dir: str):
    """Her paket için kaç kez retransmit yapıldığını gösterir."""
    retrans_per_pkt = defaultdict(int)
    for r in rows:
        if r["event"] == "RETRANSMIT":
            try:
                retrans_per_pkt[int(r["seq_num"])] += 1
            except (ValueError, KeyError):
                pass

    if not retrans_per_pkt:
        return

    seq_nums = sorted(retrans_per_pkt.keys())
    counts   = [retrans_per_pkt[s] for s in seq_nums]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(seq_nums, counts, color="#F44336", edgecolor="white")
    ax.set_xlabel("Paket Sıra Numarası (seq)")
    ax.set_ylabel("Retransmit Sayısı")
    ax.set_title("Paket Başına Retransmission Dağılımı")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "retransmit_heatmap.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  📊 {path}")


# ──────────────────────────────────────────────
#  Karşılaştırmalı Deney Grafiği
# ──────────────────────────────────────────────

def plot_comparison(experiment_results: list[dict], x_key: str, output_dir: str):
    """
    Farklı deney sonuçlarını karşılaştırır.

    experiment_results: [
        {"label": "512B", "throughput_kbps": ..., "goodput_ratio": ..., ...},
        ...
    ]
    x_key: x ekseninde kullanılacak etiket anahtarı ("label")
    """
    if not experiment_results:
        return

    labels      = [r["label"] for r in experiment_results]
    throughputs = [r["throughput_kbps"] for r in experiment_results]
    goodputs    = [r["goodput_ratio"] * 100 for r in experiment_results]
    retrans     = [r["retrans_rate"] * 100 for r in experiment_results]
    comp_times  = [r["elapsed_ms"] for r in experiment_results]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Karşılaştırmalı Deney Sonuçları", fontsize=14, fontweight="bold")

    def bar_chart(ax, values, title, ylabel, color):
        bars = ax.bar(labels, values, color=color, edgecolor="white")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=9)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)
        ax.tick_params(axis="x", rotation=15)

    bar_chart(axes[0][0], throughputs, "Throughput",        "kbps",  "#2196F3")
    bar_chart(axes[0][1], goodputs,    "Goodput Oranı",     "%",     "#4CAF50")
    bar_chart(axes[1][0], retrans,     "Retransmission",    "%",     "#FF9800")
    bar_chart(axes[1][1], comp_times,  "Tamamlanma Süresi", "ms",    "#9C27B0")

    plt.tight_layout()
    path = os.path.join(output_dir, f"comparison_{x_key}.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  📊 {path}")


# ──────────────────────────────────────────────
#  Ana Fonksiyon
# ──────────────────────────────────────────────

def analyze(log_file: str, output_dir: str = "graphs"):
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n🔍 Analiz ediliyor: {log_file}\n")

    rows    = load_log(log_file)
    metrics = compute_metrics(rows)

    # Metrikleri yazdır
    print("📈 Performans Metrikleri:")
    print(f"   Gönderilen paket  : {metrics['sent_count']}")
    print(f"   Alınan ACK        : {metrics['ack_count']}")
    print(f"   Timeout           : {metrics['timeout_count']}")
    print(f"   Retransmission    : {metrics['retrans_count']}")
    print(f"   Başarısız paket   : {metrics['fail_count']}")
    print(f"   Toplam veri       : {metrics['total_bytes']} byte")
    print(f"   Tamamlanma süresi : {metrics['elapsed_ms']} ms")
    print(f"   Throughput        : {metrics['throughput_kbps']} kbps")
    print(f"   Goodput oranı     : {metrics['goodput_ratio']}")
    print(f"   Retransmit oranı  : {metrics['retrans_rate']}")
    print(f"   Ortalama RTT      : {metrics['avg_rtt_ms']} ms")
    print(f"   Kayıp oranı       : {metrics['loss_rate']}\n")

    # JSON olarak kaydet
    json_path = os.path.join(output_dir, "metrics.json")
    with open(json_path, "w") as f:
        metrics_out = {k: v for k, v in metrics.items() if k != "rtt_values"}
        json.dump(metrics_out, f, indent=2)
    print(f"  💾 {json_path}")

    # Grafikler
    if MATPLOTLIB:
        print("\n📊 Grafikler üretiliyor:")
        plot_rtt_over_time(rows, output_dir)
        plot_event_timeline(rows, output_dir)
        plot_metrics_bar(metrics, output_dir)
        plot_retransmit_heatmap(rows, output_dir)
        print("\nTüm grafikler kaydedildi ✅")
    else:
        print("⚠ Grafik üretimi atlandı (matplotlib yok).")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetProbe Performans Analizörü")
    parser.add_argument("--log",    required=True,        help="CSV log dosyası")
    parser.add_argument("--output", default="graphs",     help="Grafiklerin kaydedileceği klasör")
    args = parser.parse_args()

    analyze(log_file=args.log, output_dir=args.output) 