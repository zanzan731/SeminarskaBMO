import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.interpolate import griddata

# ── CONFIG ──────────────────────────────────────────
ROOM_WIDTH  = 3.5   # meters
ROOM_HEIGHT = 3.0   # meters
GRID_STEP   = 0.5   # meters between measurements

# Your closet/blocked area (set to None if none)
CLOSET1 = {"x1": 0.0, "y1": 0.95, "x2": 0.5, "y2": 1.75}
CLOSET2 = {"x1": 3.0, "y1": 3.0, "x2": 3.5, "y2": 2.2}
CHAIR = {"x1": 0.9, "y1": 1.25, "x2": 1.4, "y2": 1.75}

# Label → (x, y) mapping — center of each cell
# Adjust to match YOUR labels and room layout
LABEL_COORDS = {
    "A1": (0.25, 2.75), "A2": (0.75, 2.75), "A3": (1.25, 2.75), "A4": (1.75, 2.75), "A5": (2.25, 2.75), "A6": (2.75, 2.75), "A7": (3.25, 2.75),
    "B1": (0.25, 2.25), "B2": (0.75, 2.25), "B3": (1.25, 2.25), "B4": (1.75, 2.25), "B5": (2.25, 2.25), "B6": (2.75, 2.25), "B7": (3.25, 2.25),
    "C1": (0.25, 1.75), "C2": (0.75, 1.75), "C3": (1.25, 1.75), "C4": (1.75, 1.75), "C5": (2.25, 1.75), "C6": (2.75, 1.75), "C7": (3.25, 1.75),
    "D1": (0.25, 1.25), "D2": (0.75, 1.25), "D3": (1.25, 1.25), "D4": (1.75, 1.25), "D5": (2.25, 1.25), "D6": (2.75, 1.25), "D7": (3.25, 1.25),
    "E1": (0.25, 0.75), "E2": (0.75, 0.75), "E3": (1.25, 0.75), "E4": (1.75, 0.75), "E5": (2.25, 0.75), "E6": (2.75, 0.75), "E7": (3.25, 0.75),
    "F1": (0.25, 0.25), "F2": (0.75, 0.25), "F3": (1.25, 0.25), "F4": (1.75, 0.25), "F5": (2.25, 0.25), "F6": (2.75, 0.25), "F7": (3.25, 0.25),
}
# ────────────────────────────────────────────────────

# Load CSV
df = pd.read_csv("bt_heatmap.csv", header=None,
                 names=["timestamp", "label", "rssi"])
df = df.dropna(subset=["rssi"])  # drop blocked/missing points
df["rssi"] = pd.to_numeric(df["rssi"], errors="coerce").dropna()

# If multiple readings per label, take the average
df = df.groupby("label")["rssi"].mean().reset_index()

# Map labels to coordinates
df["x"] = df["label"].map(lambda l: LABEL_COORDS[l][0])
df["y"] = df["label"].map(lambda l: LABEL_COORDS[l][1])
df = df.dropna(subset=["x", "y"])

# ── INTERPOLATION ────────────────────────────────────
# Fine grid to interpolate onto
xi = np.linspace(0, ROOM_WIDTH,  200)
yi = np.linspace(0, ROOM_HEIGHT, 200)
Xi, Yi = np.meshgrid(xi, yi)

points = df[["x", "y"]].values
values = df["rssi"].values

Zi = griddata(points, values, (Xi, Yi), method="cubic")

# ── PLOT ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 6))

heatmap = ax.contourf(Xi, Yi, Zi, levels=20, cmap="RdYlGn")
cbar = plt.colorbar(heatmap, ax=ax)
cbar.set_label("RSSI (dBm)")

# Draw measurement points
ax.scatter(df["x"], df["y"], c="black", s=20, zorder=5, label="Measurements")

# Annotate with labels
for _, row in df.iterrows():
    ax.annotate(row["label"], (row["x"], row["y"]),
                textcoords="offset points", xytext=(5, 5), fontsize=7)

# hotspot
ax.scatter(1.0, 2.75, c="blue", s=200, zorder=5, label="Hotspot")

# closet 
rect = Rectangle((CLOSET1["x1"], CLOSET1["y1"]),
                    CLOSET1["x2"] - CLOSET1["x1"],
                    CLOSET1["y2"] - CLOSET1["y1"],
                    linewidth=2, edgecolor="black",
                    facecolor="grey", alpha=0.6, zorder=6)
ax.add_patch(rect)
ax.text((CLOSET1["x1"]+CLOSET1["x2"])/2, (CLOSET1["y1"]+CLOSET1["y2"])/2,
        "closet", ha="center", va="center", fontsize=9, zorder=7)

rect = Rectangle((CLOSET2["x1"], CLOSET2["y1"]),
                    CLOSET2["x2"] - CLOSET2["x1"],
                    CLOSET2["y2"] - CLOSET2["y1"],
                    linewidth=2, edgecolor="black",
                    facecolor="grey", alpha=0.6, zorder=6)
ax.add_patch(rect)
ax.text((CLOSET2["x1"]+CLOSET2["x2"])/2, (CLOSET2["y1"]+CLOSET2["y2"])/2,
        "closet", ha="center", va="center", fontsize=9, zorder=7)

rect = Rectangle((CHAIR["x1"], CHAIR["y1"]),
                    CHAIR["x2"] - CHAIR["x1"],
                    CHAIR["y2"] - CHAIR["y1"],
                    linewidth=2, edgecolor="black",
                    facecolor="grey", alpha=0.6, zorder=6)
ax.add_patch(rect)
ax.text((CHAIR["x1"]+CHAIR["x2"])/2, (CHAIR["y1"]+CHAIR["y2"])/2,
        "metal chair", ha="center", va="center", fontsize=9, zorder=7)

ax.set_xlim(0, ROOM_WIDTH)
ax.set_ylim(0, ROOM_HEIGHT)
ax.set_xlabel("meters")
ax.set_ylabel("meters")
ax.set_title("Bluetooth RSSI Heatmap")
ax.legend()
ax.set_aspect("equal")

plt.tight_layout()
plt.savefig("heatmap.png", dpi=150)
plt.show()
