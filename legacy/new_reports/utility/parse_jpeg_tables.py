import cv2, numpy as np, pytesseract, pandas as pd
from pathlib import Path
import shutil

BASE_DIR = Path(r"c:\dev\LO25\parse_images")
IMAGES = [
    r"c:\dev\LO25\parse_images\img1a.jpeg",
    r"c:\dev\LO25\parse_images\img1b.jpeg",
    r"c:\dev\LO25\parse_images\img1c.jpeg",
    r"c:\dev\LO25\parse_images\img2a.jpeg",
    r"c:\dev\LO25\parse_images\img2b.jpeg",

]
CROPS_DIR = BASE_DIR / "debug" / "crops"
DEBUG_DIR = BASE_DIR / "debug" / "rois"
OUTPUT_DIR = BASE_DIR / "output"

if CROPS_DIR.exists():
    shutil.rmtree(CROPS_DIR)
if DEBUG_DIR.exists():
    shutil.rmtree(DEBUG_DIR)
if OUTPUT_DIR.exists():
    shutil.rmtree(OUTPUT_DIR)

CROPS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def process_image(img_path):
    """Process a single image and extract rows using horizontal line detection"""
    img = cv2.imread(img_path)
    assert img is not None, f"Could not read {img_path}"

    img_name = Path(img_path).stem
    print(f"\nProcessing {img_name}...")

    scale = 2.0
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    H, W = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)


    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (W//20, 1))  # Increased from W//30
    h_lines_blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, h_kernel)  # Dark lines
    h_lines_tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, h_kernel)  # Light lines
    h_lines_enhanced = cv2.add(h_lines_blackhat, h_lines_tophat)  # Both

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, H//20))  # Increased from H//30
    v_lines_blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, v_kernel)  # Dark lines
    v_lines_tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, v_kernel)  # Light lines
    v_lines_enhanced = cv2.add(v_lines_blackhat, v_lines_tophat)  # Both

    gray_enhanced = cv2.addWeighted(gray, 1.0, h_lines_enhanced, 0.6, 0)  # Increased from 0.5 to 0.8
    gray_enhanced = cv2.addWeighted(gray_enhanced, 1.0, v_lines_enhanced, 0.6, 0)

    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_original_gray.png"), gray)
    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_enhanced_gray.png"), gray_enhanced)
    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_h_lines_extracted.png"), h_lines_enhanced)
    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_v_lines_extracted.png"), v_lines_enhanced)

    edges = cv2.Canny(gray_enhanced, 20, 80, apertureSize=3)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    lines_h = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, minLineLength=W//6, maxLineGap=60)

    sobelx = cv2.Sobel(gray_enhanced, cv2.CV_64F, 1, 0, ksize=3)
    sobelx = np.abs(sobelx).astype(np.uint8)

    _, sobelx_thresh = cv2.threshold(sobelx, 15, 255, cv2.THRESH_BINARY)  # Lowered from 20 to 15

    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_vertical_edges.png"), sobelx_thresh)

    v_continuity = np.sum(sobelx_thresh > 0, axis=0)

    v_continuity_smooth = np.convolve(v_continuity, np.ones(15)/15, mode='same')  # Widen smoothing from 10 [comment clipped]

    min_continuity = H * 0.25  # Lowered from 0.3

    mean_cont = np.mean(v_continuity_smooth)
    std_cont = np.std(v_continuity_smooth)
    threshold_v = mean_cont + std_cont * 0.1  # Lowered from 0.2 to 0.1

    print(f"  Vertical edge continuity stats: mean={mean_cont:.1f}, std={std_cont:.1f}, threshold={threshold_v:.1f}")

    v_positions = []
    for i in range(1, len(v_continuity_smooth) - 1):
        if v_continuity_smooth[i] > min_continuity and v_continuity_smooth[i] > threshold_v:
            if v_continuity_smooth[i] > v_continuity_smooth[i-1] and v_continuity_smooth[i] > v_continuity_smooth[i+1]:
                if not any(abs(i - existing) < 30 for existing in v_positions):
                    v_positions.append(i)
                    print(f"    Found vertical line at x={i}, continuity={v_continuity_smooth[i]:.1f}")

    h_positions = []

    if lines_h is not None:
        for line in lines_h:
            x1, y1, x2, y2 = line[0]

            if x2 - x1 == 0:
                angle = 90
            else:
                angle = abs(np.degrees(np.arctan((y2 - y1) / (x2 - x1))))

            if angle < 10:
                y_pos = (y1 + y2) // 2
                line_len = abs(x2 - x1)
                if line_len > W * 0.3:
                    if not any(abs(y_pos - existing) < 25 for existing in h_positions):
                        h_positions.append(y_pos)

    h_positions.sort()
    if not h_positions or h_positions[0] > 10:
        h_positions.insert(0, 0)
    if not h_positions or h_positions[-1] < H - 10:
        h_positions.append(H)

    v_positions.sort()
    if not v_positions or v_positions[0] > 10:
        v_positions.insert(0, 0)
    if not v_positions or v_positions[-1] < W - 10:
        v_positions.append(W)

    print(f"  Found {len(h_positions)} horizontal lines, {len(v_positions)} vertical lines")

    debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for y in h_positions:
        cv2.line(debug_img, (0, y), (W, y), (0, 255, 0), 2)
    for x in v_positions:
        cv2.line(debug_img, (x, 0), (x, H), (255, 0, 0), 2)
    cv2.imwrite(str(DEBUG_DIR / f"{img_name}_detected_lines.png"), debug_img)

    rows_out = []
    padding = 5

    for row_idx in range(len(h_positions) - 1):
        y1, y2 = h_positions[row_idx], h_positions[row_idx + 1]

        y1 = max(0, y1 + padding)
        y2 = min(H, y2 - padding)

        if (y2 - y1) < 15:
            continue

        row_crop = img[y1:y2, 0:W]

        pad = 10
        row_crop = cv2.copyMakeBorder(row_crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(255, 255, 255))

        g = cv2.cvtColor(row_crop, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        cv2.imwrite(str(CROPS_DIR / f"{img_name}_row{row_idx}.png"), binary)

        txt = pytesseract.image_to_string(binary, config="--psm 6 --oem 3")
        rows_out.append([txt.strip()])

    print(f"  Extracted {len(rows_out)} rows")

    if rows_out:
        df = pd.DataFrame(rows_out)
        out_csv = OUTPUT_DIR / f"{img_name}.csv"
        df.to_csv(out_csv, index=False, header=False)
        print(f"  Saved to {out_csv.name}")


for img_path in IMAGES:
    process_image(img_path)
