"""
RSSI Plotter — POCO X7 Pro signal strength analysis
Usage:
    python plot_rssi.py                        # uses current directory
    python plot_rssi.py /path/to/csv/files     # uses specified directory
    python plot_rssi.py file1.csv file2.csv    # specific files

Files must be named like: rssi_meritve_N_naprava_Dm.csv
  N = number of devices, D = distance in meters
"""

import sys
import re
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from pathlib import Path

DEVICE_NAME = "POCO X7 Pro"
FILENAME_PATTERN = re.compile(r"(\d+)_naprava_(\d+)m", re.IGNORECASE)


def load_files(paths):
    data = []
    skipped = []

    for path in paths:
        m = FILENAME_PATTERN.search(Path(path).name)
        if not m:
            skipped.append((path, "filename doesn't match pattern"))
            continue

        devices, distance = int(m.group(1)), int(m.group(2))

        try:
            df = pd.read_csv(path)
        except Exception as e:
            skipped.append((path, str(e)))
            continue

        if "Device_Name" not in df.columns or "RSSI" not in df.columns:
            skipped.append((path, "missing Device_Name or RSSI column"))
            continue

        poco = df[df["Device_Name"] == DEVICE_NAME]["RSSI"].dropna().tolist()
        if not poco:
            skipped.append((path, f"no '{DEVICE_NAME}' readings found"))
            continue

        data.append({
            "devices": devices,
            "distance": distance,
            "values": poco,
            "mean": round(np.mean(poco), 1),
            "median": round(np.median(poco), 1),
            "std": round(np.std(poco), 1),
            "min": int(np.min(poco)),
            "max": int(np.max(poco)),
            "n": len(poco),
            "file": Path(path).name,
        })

    data.sort(key=lambda d: (d["distance"], d["devices"]))

    if skipped:
        print("\nSkipped files:")
        for path, reason in skipped:
            print(f"  {Path(path).name}: {reason}")

    return data


def collect_paths(args):
    if not args:
        return sorted(glob.glob("*.csv"))

    paths = []
    for arg in args:
        if os.path.isdir(arg):
            paths.extend(sorted(glob.glob(os.path.join(arg, "*.csv"))))
        elif os.path.isfile(arg):
            paths.append(arg)
        else:
            print(f"Warning: '{arg}' not found, skipping.")
    return paths


def plot(data):
    distances = sorted(set(d["distance"] for d in data))
    device_counts = sorted(set(d["devices"] for d in data))

    # Color palettes
    dist_colors = plt.cm.viridis(np.linspace(0.15, 0.85, max(len(distances), 1)))
    dev_colors  = plt.cm.plasma(np.linspace(0.15, 0.85, max(len(device_counts), 1)))

    fig = plt.figure(figsize=(16, 12), facecolor="#0f1117")
    fig.suptitle(
        f"{DEVICE_NAME} — RSSI Signal Strength Analysis",
        fontsize=16, fontweight="bold", color="white", y=0.98
    )

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
                           left=0.07, right=0.97, top=0.93, bottom=0.07)

    def style_ax(ax, title):
        ax.set_facecolor("#1a1d27")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.set_title(title, color="white", fontsize=11, fontweight="bold")

    # ── 1. Line: RSSI vs Distance, grouped by device count ──────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    style_ax(ax1, "Mean RSSI vs Distance")
    for i, dev in enumerate(device_counts):
        pts = [(d["distance"], d["mean"]) for d in data if d["devices"] == dev]
        pts.sort()
        if pts:
            xs, ys = zip(*pts)
            ax1.plot(xs, ys, "o-", color=dev_colors[i], linewidth=2,
                     markersize=6, label=f"{dev} device{'s' if dev > 1 else ''}")
    ax1.set_xlabel("Distance (m)", color="white")
    ax1.set_ylabel("RSSI (dBm)", color="white")
    ax1.legend(fontsize=9, labelcolor="white", facecolor="#2a2d3a", edgecolor="#444")
    ax1.tick_params(colors="white")
    ax1.grid(True, color="#2a2d3a", linewidth=0.8)
    for spine in ax1.spines.values():
        spine.set_edgecolor("#333")

    # ── 2. Line: RSSI vs Device count, grouped by distance ─────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    style_ax(ax2, "Mean RSSI vs Device Count")
    for i, dist in enumerate(distances):
        pts = [(d["devices"], d["mean"]) for d in data if d["distance"] == dist]
        pts.sort()
        if pts:
            xs, ys = zip(*pts)
            ax2.plot(xs, ys, "s-", color=dist_colors[i], linewidth=2,
                     markersize=6, label=f"{dist} m")
    ax2.set_xlabel("Number of Devices", color="white")
    ax2.set_ylabel("RSSI (dBm)", color="white")
    ax2.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax2.legend(fontsize=9, labelcolor="white", facecolor="#2a2d3a", edgecolor="#444")
    ax2.tick_params(colors="white")
    ax2.grid(True, color="#2a2d3a", linewidth=0.8)
    for spine in ax2.spines.values():
        spine.set_edgecolor("#333")

    # ── 3. Box plot: distribution per file ──────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    style_ax(ax3, "RSSI Distribution per File")
    labels = [f"{d['devices']}dev\n{d['distance']}m" for d in data]
    bp = ax3.boxplot(
        [d["values"] for d in data],
        labels=labels, patch_artist=True, notch=False,
        medianprops=dict(color="#f0c040", linewidth=2),
        whiskerprops=dict(color="#888"),
        capprops=dict(color="#888"),
        flierprops=dict(marker="o", color="#f05050", markersize=3, alpha=0.6),
    )
    colors_cycle = plt.cm.cool(np.linspace(0.1, 0.9, len(data)))
    for patch, color in zip(bp["boxes"], colors_cycle):
        patch.set_facecolor((*color[:3], 0.5))
        patch.set_edgecolor("white")
    ax3.set_xlabel("File (devices @ distance)", color="white")
    ax3.set_ylabel("RSSI (dBm)", color="white")
    ax3.tick_params(colors="white", labelsize=8)
    ax3.grid(True, axis="y", color="#2a2d3a", linewidth=0.8)
    for spine in ax3.spines.values():
        spine.set_edgecolor("#333")

    # ── 4. Heatmap: mean RSSI by devices × distance ─────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    style_ax(ax4, "Mean RSSI Heatmap")
    matrix = np.full((len(device_counts), len(distances)), np.nan)
    for d in data:
        ri = device_counts.index(d["devices"])
        ci = distances.index(d["distance"])
        matrix[ri, ci] = d["mean"]

    im = ax4.imshow(matrix, aspect="auto", cmap="RdYlGn",
                    vmin=np.nanmin(matrix) - 3, vmax=np.nanmax(matrix) + 3)
    ax4.set_xticks(range(len(distances)))
    ax4.set_xticklabels([f"{d}m" for d in distances], color="white", fontsize=9)
    ax4.set_yticks(range(len(device_counts)))
    ax4.set_yticklabels([f"{d} dev" for d in device_counts], color="white", fontsize=9)
    ax4.set_xlabel("Distance", color="white")
    ax4.set_ylabel("Device Count", color="white")
    ax4.tick_params(colors="white")
    for spine in ax4.spines.values():
        spine.set_edgecolor("#333")

    for ri in range(len(device_counts)):
        for ci in range(len(distances)):
            val = matrix[ri, ci]
            if not np.isnan(val):
                ax4.text(ci, ri, f"{val:.1f}", ha="center", va="center",
                         fontsize=9, fontweight="bold",
                         color="black" if val > np.nanmean(matrix) else "white")

    cbar = fig.colorbar(im, ax=ax4, fraction=0.046, pad=0.04)
    cbar.ax.yaxis.set_tick_params(color="white", labelcolor="white")
    cbar.set_label("dBm", color="white")

    out_path = "rssi_poco_x7_pro.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nPlot saved to: {os.path.abspath(out_path)}")
    plt.show()


def print_summary(data):
    print(f"\n{'─'*60}")
    print(f"{'POCO X7 Pro RSSI Summary':^60}")
    print(f"{'─'*60}")
    print(f"{'File':<32} {'Dev':>4} {'Dist':>5} {'n':>4} {'Mean':>7} {'Std':>6} {'Min':>5} {'Max':>5}")
    print(f"{'─'*60}")
    for d in data:
        print(f"{d['file']:<32} {d['devices']:>4} {d['distance']:>4}m {d['n']:>4} "
              f"{d['mean']:>6.1f} {d['std']:>5.1f} {d['min']:>5} {d['max']:>5}")
    print(f"{'─'*60}")
    all_vals = [v for d in data for v in d["values"]]
    print(f"{'TOTAL':<32} {'':>4} {'':>5} {len(all_vals):>4} "
          f"{np.mean(all_vals):>6.1f} {np.std(all_vals):>5.1f} "
          f"{min(all_vals):>5} {max(all_vals):>5}")
    print(f"{'─'*60}\n")


def main():
    paths = collect_paths(sys.argv[1:])

    if not paths:
        print("No CSV files found. Pass a directory, specific files, or run from a folder containing CSVs.")
        sys.exit(1)

    print(f"Found {len(paths)} CSV file(s). Loading '{DEVICE_NAME}' readings...")
    data = load_files(paths)

    if not data:
        print(f"No usable data found for '{DEVICE_NAME}'.")
        sys.exit(1)

    print(f"Loaded {len(data)} file(s) with {sum(d['n'] for d in data)} total readings.")
    print_summary(data)
    plot(data)


if __name__ == "__main__":
    main()