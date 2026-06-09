# HLK-LD2460 — Hardware & Enclosure Notes

Source: *HLK-LD2460 2T4R Multi Target Trajectory Tracking Module Manual V1.1*
(Shenzhen Hi-Link Electronic Co., Ltd) and *Serial Port Communication Protocol V1.0*.
Captured 2026-06-09 for a future 3D-printed enclosure.

## Board dimensions (Figure 1, "Module dimension annotation")

All values in **mm**.

- **Overall PCB outline: 32.00 (W) × 49.50 (H)**.
- Top-edge feature offsets across the width: `12.22`, then `2.00`, then `13.78`.
- Bottom-edge feature offsets: `13.69` and `16.32`.
  (These locate the antenna centre and the two mounting points / dots shown in
  the figure. Exact hole diameter and PCB thickness are **not given** in the
  manual — measure the physical board before finalising the enclosure. PCB
  thickness is typically ~1.0–1.6 mm; the antenna side carries SMD components and
  shielded radar cans, so allow component height clearance, est. 3–4 mm.)
- **Action item:** caliper-measure mounting-hole diameter, hole-centre spacing,
  PCB thickness, and tallest component height before modelling the enclosure.

## Connectors / pinout

12 pins total (Table 1, "Definition of Radar Pin"). Two UARTs are exposed.

| Pin | Name  | Type | Function                                   |
|-----|-------|------|--------------------------------------------|
| 1   | 5V    | PWR  | DC 5 V power input                         |
| 2   | GND   | GND  | Ground                                     |
| 3   | Tx1   | O    | Serial port 1 output                       |
| 4   | Rx1   | I    | Serial port 1 input                        |
| 5   | VDD33 | PWR  | 3.3 V / NC (only used during debugging)    |
| 6   | GND   | GND  | Ground                                     |
| 7   | Tx2   | O    | **Serial 2 output — radar data + responses** |
| 8   | Rx2   | I    | **Serial 2 input — command reception**     |
| 9   | IO1   | I/O  | GPO1 / reserved                            |
| 10  | IO2   | I/O  | GPO2 / reserved                            |
| 11  | IO3   | I/O  | GPO3 / reserved                            |
| 12  | IO4   | I/O  | GPO4 / reserved                            |

**Use UART2 (Tx2 = pin 7, Rx2 = pin 8) for this project.** Cross TX↔RX, share a
common ground, supply 5 V. The enclosure must leave the connector header
accessible (or route a cable out through a strain-relieved slot).

## Electrical

- Working frequency: **24 – 24.25 GHz**, bandwidth 250 MHz, FMCW, EIRP 13 dBm.
- Supply: **5 V** (acceptable 4.2 – 5.4 V); average current **≤250 mA**, peak 180 mA.
- Operating / storage temperature: **−40 °C to +85 °C**.
- Composition: two 1Tx/2Rx 24 GHz radar chips, microstrip antenna, MCU,
  Bluetooth SoC, support circuitry.
- Startup: ~1 s self-init (noise floor evaluation) before stable reporting.

## Detection capability (relevant to placement)

- People: ≥3 stationary (sitting/standing), up to 5 moving.
- Range (bare board): dynamic ≥6 m within ±50° (≥5.5 m at ±50–60°); static ≥5 m
  within ±50° (≥4.5 m at ±50–60°).
- Range resolution 0.75 m; distance accuracy ≤0.3 m.
- Detection FOV: horizontal **120°**, vertical **90°**; working beam is a 3-D fan
  of ~90° horizontal × ~50° vertical. Angle accuracy ≤5°.
- Motion trigger time 0.5 s; stationary presence hold ≤30 s.

## Coordinate system (confirms signed X in the protocol)

- **Side-mounted:** X ∈ **[−6, 6] m** (right of antenna = +X), Y ∈ [0, 6] m
  (front = +Y), angle ∈ [−60°, +60°], 0° = normal.
- **Top-mounted (ceiling):** X ∈ [−4, 4] m, Y ∈ [−4, 4] m, angle ∈ [0°, 360°].
- Because X spans negative values, the reported X (and top-mount Y) are **signed
  16-bit** little-endian, unit 0.1 m — this is the decode used in the software.

## Mounting / orientation (drives enclosure geometry)

- **Side-hang (wall):** angle between module and wall **25–40°**, height
  **2.2–2.7 m** (factory default 30°, 2.6 m). The enclosure likely needs a wedge
  / tilt bracket in this range.
- **Top (ceiling):** module horizontal, height **2.5–3 m**, antenna facing down.
- The installation mode (side vs top) must also be set in firmware to match the
  physical placement (see protocol command tables 9–12).

## Enclosure design implications

- **RF window:** 24 GHz signals pass through thin plastic, thin wood, and glass,
  but **not metal**. A plain plastic (PETG/ABS/ASA) cover over the antenna face is
  fine — keep it thin and avoid metallic paint/foil over the antenna. ASA/PETG
  preferred if mounted near a window or warm location (UV/temp).
- **No metal** in front of the antenna; keep a small standoff air gap between the
  antenna face and the cover.
- Provide **connector access** for the UART2 header (pin 7/8) + 5 V/GND, with
  strain relief.
- Support the **side-mount 25–40° tilt** and **top-mount flat** options — either
  two enclosure variants or an adjustable wedge bracket.
- Allow component-height clearance on the antenna side; don't clamp the PCB
  against components.
- Mild thermal load (≤1.3 W); passive venting is sufficient, but avoid a fully
  sealed cavity if used at the warm end of the range.

## Reference files (kept locally, git-ignored due to size)

- `protocol.pdf` — HLK-LD2460 Serial Port Communication Protocol V1.0.
- `module_manual.pdf` — HLK-LD2460 module manual V1.1 (dimensions in Figure 1).
- Official resources (Google Drive, includes the Windows config/test tool
  `HLK-2460_Tool_install.exe`):
  https://drive.google.com/drive/folders/1JkImVaRfSgP8taq5W4aW_bCxlcqeHVan
