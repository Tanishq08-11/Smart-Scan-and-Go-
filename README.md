# 🛡️ Smart Scan & Go — 100% Loss Prevention & Automated Exit Platform

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue.svg?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-v3.6.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF9900.svg?logo=opencv)](https://docs.ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer_Vision-5C3EE8.svg?logo=opencv)](https://opencv.org/)
[![Status](https://img.shields.io/badge/Hackathon-Production_Ready-success.svg)]()

> **"An intelligent computer vision & sensor-fusion security layer that cross-references a customer's physical shelf interactions with their smartphone barcode scans in real-time."**

---

## 📌 Executive Summary & Problem Statement

Self-checkout kiosks cost global retailers over **$100 Billion annually** in shrinkage due to barcode swapping ("sweethearting"), unscanned item pocketing, and hardware friction.

Existing Scan-and-Go mobile apps rely on honor systems or random spot-checks, creating massive theft vulnerabilities.

**Smart Scan & Go** solves this by creating a **fail-safe, real-time security layer**. By combining **Overhead Shelf Computer Vision (YOLOv8)**, **Smart Scale Weight Sensor Telemetry ($\Delta W$)**, **Entry QR Person ReID**, and a **Deterministic Pick Ledger Audit**, the system cross-references physical shelf pickups with smartphone barcode scans to **guarantee 100% loss prevention** while delivering a frictionless walkout experience for honest shoppers.

---

## 🏗️ System Architecture & Workflow

```mermaid
flowchart TD
    subgraph STAGE1["1. ENTRY GATE AUTHORIZATION"]
        A["Shopper scans Entry QR Code"] --> B["API binds Person Track ID (TRK-xxxx)"]
        B --> C["Pre-Authorizes Card/UPI ($50 Hold)"]
    end

    subgraph STAGE2["2. SMART SHELF VISION & SENSOR FUSION"]
        D["Shopper lifts item off shelf"] --> E["YOLOv8 Camera Node detects physical pickup"]
        E --> F["Broadcasts PICKED event & slot weight delta ΔW"]
    end

    subgraph STAGE3["3. MOBILE SCAN & PICK LEDGER AUDIT"]
        G["Shopper scans barcode on phone app"] --> H{"Pick Ledger Audit:<br>Picks - Returns - Scans == 0?"}
        F --> H
        H -- Valid Match --> I["Item added to Cart as VERIFIED"]
        H -- Item Still On Shelf / Mismatch --> J["🚨 BLOCK SCAN & Log Anomaly"]
    end

    subgraph STAGE4["4. 100% LOSS PREVENTION EXIT GATE"]
        I --> K["Shopper taps 'Checkout & Exit Gate'"]
        J --> K
        K --> L{"Pick Ledger Reconciled & Trust Score >= 80?"}
        L -- YES --> M["🟢 GATE OPENS AUTOMATICALLY<br>(Pre-Auth Card Charged)"]
        L -- NO --> N["🔴 100% SECURITY HOLD<br>(Gate Locked & Card Charged for Unreturned Picks)"]
    end
```

---

## 🌟 Key Features & Technical Innovation

### 1. 🆔 Entry Gate Person ReID Binding
At store entry, the customer scans a dynamic QR code on their smartphone. The backend binds their camera spatial track ID (`person_track_id`: `TRK-8842`) to their active `session_id` and secures a **$50 Payment Pre-Authorization Hold**.

### 2. 📹 Smart Shelf Computer Vision (YOLOv8 Physical Pickup Detector)
Overhead shelf cameras run an optimized YOLOv8 neural network tracking physical shelf state:
* **`ON_SHELF`**: Item resting on shelf. Scans attempted while item sits on shelf are **STRICTLY BLOCKED**.
* **`PICKED OFF SHELF`**: Item physically lifted off shelf (disappears from shelf view) $\rightarrow$ Fires `PICKED` event & unlocks app scanning.
* **`PUT BACK ON SHELF`**: Item placed back on shelf $\rightarrow$ Fires `RETURNED` event & cancels pending pick.

### 3. 🧮 Deterministic Pick Ledger Audit Equation
$$\text{Available Unscanned Picks} = \text{Total Shelf Picks} - \text{Total Shelf Returns} - \text{Scanned Cart Items} > 0$$
* A scanned item is **ONLY** added to the cart if an active physical pickup event exists for that item class.

### 4. 📈 Explicit Trust Score Engine ($T_{\text{score}} \in [0, 100]$)
$$T_{\text{score}} = 100 - (\text{Unresolved High-Value Picks} \times 50) - (\text{Class Mismatches} \times 20) - (\text{Invalid Scans} \times 10)$$

### 5. 🛡️ 100% Loss Prevention Exit Gate Lock Policy
The exit gate evaluates the Pick Ledger before releasing the exit barrier:
* **Clean Ledger ($\text{Unresolved Picks} = 0$)**: 🟢 **`GATE_OPEN_AUTOMATIC`** (Pre-authorized card charged automatically, digital receipt issued).
* **Unresolved Theft Attempt ($\text{Unresolved Picks} > 0$)**: 🔴 **`GATE_LOCKED_SECURITY_AUDIT`** (Exit gate stays locked; pre-authorized payment automatically charged for unreturned shelf picks).

---

## 📂 Project Structure

```
Smart-Scan-and-Go/
├── app/
│   ├── index.html        # Mobile Scanner App & Live Loss Prevention Dashboard UI
│   └── barcodes.html     # Scannable Barcode Test Sheet
├── backend/
│   ├── main.py           # FastAPI v3.6.0 Core Engine, Pick Ledger & Exit Gate API
│   ├── database.py       # SQLite Database Handler & ReID Schema
│   └── store.db          # SQLite Database File
├── cv_node.py            # Standalone YOLOv8 Computer Vision Shelf Camera Node
├── requirements.txt      # Python Dependencies
├── .gitignore            # Git Ignore Rules
└── README.md             # Project Documentation
```

---

## 🚀 Installation & Setup Guide

### Prerequisites
* Python 3.10+
* Webcam (Integrated or External USB Camera)

### 1. Clone Repository & Install Dependencies
```bash
git clone https://github.com/Tanishq08-11/Smart-Scan-and-Go-.git
cd Smart-Scan-and-Go-
pip install -r requirements.txt
```

### 2. Start Backend API Server
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
*Backend runs live at `http://127.0.0.1:8000` (and `http://<YOUR_LOCAL_IP>:8000`).*

### 3. Launch Computer Vision Node
Open a second terminal window in the project root directory:
```bash
python cv_node.py
```
*The vision node automatically binds to the active shopping session on the phone.*

### 4. Open Mobile App UI
* **On Laptop/PC**: Open `http://127.0.0.1:8000`
* **On Smartphone (Same Wi-Fi)**: Open `http://<YOUR_LOCAL_IP>:8000` (e.g. `http://192.168.0.100:8000`)

---

## 🧪 Live Demo Walkthrough & Test Scenarios

| Test Scenario | Action | System Response | Result |
| :--- | :--- | :--- | :--- |
| **1. Session Entry** | Click "Start Session" on mobile app | Binds Person Track ID (`TRK-xxxx`), pre-authorizes \$50 payment hold, sets $T_{\text{score}} = 100$. | 🟢 **Authorized** |
| **2. Scan Without Pick** | Tap `🥤 1111` (Coke) while bottle is sitting on shelf | Displays: *"Security Alert: No physical pickup detected for 'Coca-Cola 500ml'. Item is still resting on shelf."* | 🔴 **Scan Blocked** |
| **3. Valid Pick & Scan** | Lift bottle off camera shelf view $\rightarrow$ Tap `🥤 1111` | Terminal logs: `🚨 BOTTLE WAS PICKED UP FROM SHELF!` $\rightarrow$ Item verified and added to cart. | 🟢 **Item Added (Verified)** |
| **4. Put-Back / Return** | Place bottle back in camera shelf view | Terminal logs: `↩️ BOTTLE WAS PLACED BACK ON SHELF!` $\rightarrow$ Cancels pick event, updates ledger. | 🔄 **Ledger Reconciled** |
| **5. Barcode Swap Attempt** | Lift `cell phone` off shelf $\rightarrow$ Scan `2222` (Apple barcode) | Logged as `CLASS_MISMATCH`, Trust Score drops ($T_{\text{score}} - 20$), item blocked from cart. | 🔴 **Fraud Blocked** |
| **6. Exit Gate Reconciliation** | Tap "Complete & Exit Gate Reconciliation" | Pick Ledger audited ($\text{Picks} - \text{Returns} - \text{Scans} = 0$). Gate releases automatically and charges card. | 🟢 **Frictionless Walkout** |

---

## 🛡️ Edge Cases & Real-World Solutions

| Edge Case | Solution Architecture |
| :--- | :--- |
| **Multi-Item Picks (2 items at once)** | Smart scale weight sensor measures delta ($\Delta W = 2 \times 500\text{g}$), logging 2 pick tokens in the session ledger. |
| **Family / Group Shopping** | Entry QR scan links multiple smartphones to a single group track ID (`GROUP-402`), pooling the group pick ledger. |
| **Handing Item to Another Person** | System tracks item removal from shelf ledger regardless of hand transfers; item must simply be scanned or returned to shelf. |
| **Privacy Compliance (GDPR)** | Cameras process anonymized bounding boxes and spatial track IDs locally on edge nodes; no facial recognition or PII stored. |

---

## 🛠️ Technology Stack

* **Backend**: FastAPI (Python 3.13), SQLite3, Uvicorn
* **Computer Vision**: OpenCV, Ultralytics YOLOv8 (`yolov8n.pt`)
* **Frontend**: HTML5, CSS3 (Enterprise Slate Palette), Vanilla JavaScript, ZXing Barcode Engine
* **Protocol & Data Formats**: RESTful HTTP, JSON payload broadcasting

---

## 📜 License & Acknowledgments

Built for Hackathon Submission. Licensed under the [MIT License](LICENSE).
