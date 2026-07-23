import os, json, io
import numpy as np
import cairosvg
from PIL import Image
import cv2

LUCIDE_DIR = "/sessions/epic-loving-franklin/node_modules/lucide-static/icons"
MASK_SIZE = 128
DILATE = 3

def render_lucide(name):
    path = os.path.join(LUCIDE_DIR, name + ".svg")
    with open(path, "rb") as f:
        s = f.read().decode("utf-8")
    s = s.replace("currentColor", "#000000")
    return cairosvg.svg2png(bytestring=s.encode("utf-8"), output_width=256, output_height=256,
                             background_color="white")

def tight_mask(png_bytes, size=MASK_SIZE, dilate=DILATE):
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    arr = np.array(img)
    mask = (arr < 250).astype(np.uint8)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.zeros((size, size), dtype=bool)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = mask[y0:y1+1, x0:x1+1]
    crop_img = Image.fromarray((crop * 255).astype(np.uint8))
    w, h = crop_img.size
    side = max(w, h)
    padded = Image.new("L", (side, side), 0)
    padded.paste(crop_img, ((side - w) // 2, (side - h) // 2))
    resized = np.array(padded.resize((size, size)))
    m = (resized > 127).astype(np.uint8)
    if dilate > 0:
        kernel = np.ones((dilate, dilate), np.uint8)
        m = cv2.dilate(m, kernel, iterations=1)
    return m.astype(bool)

def main():
    names = sorted(fn[:-4] for fn in os.listdir(LUCIDE_DIR) if fn.endswith(".svg"))
    masks = np.zeros((len(names), MASK_SIZE * MASK_SIZE), dtype=bool)
    kept_names = []
    idx = 0
    for name in names:
        try:
            png = render_lucide(name)
            m = tight_mask(png)
        except Exception as e:
            print("FAIL", name, e)
            continue
        masks[idx] = m.flatten()
        kept_names.append(name)
        idx += 1
    masks = masks[:idx]
    np.save("/sessions/epic-loving-franklin/work/lucide_masks.npy", masks)
    with open("/sessions/epic-loving-franklin/work/lucide_mask_names.json", "w") as f:
        json.dump(kept_names, f)
    print("done:", len(kept_names), "masks, shape", masks.shape)

if __name__ == "__main__":
    main()
