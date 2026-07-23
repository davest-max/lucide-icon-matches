import os, re, json, io
from lxml import etree
import cairosvg
from PIL import Image
import imagehash

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {None: SVG_NS, "xlink": "http://www.w3.org/1999/xlink"}

def repair_svg_bytes(raw: bytes):
    """Recover-parse possibly-broken/JSX-contaminated svg files with lxml, return
    a clean serialized <svg> string containing just the first well-formed icon,
    or None if nothing salvageable."""
    # Strip common JSX-spread leftovers that break the *opening* tag itself,
    # which lxml's recovery can't route around (e.g. `<svg ...props fill="none">`).
    raw = re.sub(rb'\.\.\.props\b', b'', raw)
    raw = re.sub(rb'\{\.\.\.[a-zA-Z0-9_]*\}', b'', raw)
    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        root = etree.fromstring(raw, parser=parser)
    except Exception:
        return None
    if root is None:
        return None
    tag = etree.QName(root).localname
    if tag != "svg":
        return None
    # does it contain any drawable element?
    drawable_tags = {"path", "circle", "rect", "polygon", "polyline", "ellipse", "line", "g"}
    has_drawable = any(etree.QName(el).localname in drawable_tags for el in root.iter())
    if not has_drawable:
        return None
    try:
        return etree.tostring(root)
    except Exception:
        return None

def normalize_to_black(svg_bytes: bytes) -> bytes:
    """Force all fills/strokes to black (keep 'none'), strip currentColor, drop opacity<1 issues."""
    s = svg_bytes.decode("utf-8", errors="ignore")
    # currentColor -> black
    s = re.sub(r'currentColor', '#000000', s)
    # fill="#hex" or fill="name" (not none) -> black
    def repl_attr(m):
        attr, val = m.group(1), m.group(2)
        if val.strip().lower() in ("none", "transparent"):
            return m.group(0)
        return f'{attr}="#000000"'
    s = re.sub(r'\b(fill|stroke)="([^"]*)"', repl_attr, s)
    # style="fill:...;stroke:..." inline
    def repl_style(m):
        style = m.group(1)
        def sub_prop(mm):
            prop, val = mm.group(1), mm.group(2).strip()
            if val.lower() in ("none", "transparent"):
                return f"{prop}:{val}"
            return f"{prop}:#000000"
        style = re.sub(r'\b(fill|stroke)\s*:\s*([^;"]+)', sub_prop, style)
        return f'style="{style}"'
    s = re.sub(r'style="([^"]*)"', repl_style, s)
    # remove fill-opacity/stroke-opacity reductions that would fade the silhouette
    s = re.sub(r'(fill|stroke)-opacity="[^"]*"', r'\1-opacity="1"', s)
    # ensure a white background isn't required; we'll composite later
    return s.encode("utf-8")

def render_png(svg_bytes: bytes, size=128):
    return cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size,
                             background_color="white")

def to_phash(png_bytes):
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    return imagehash.phash(img, hash_size=8)

def process_file(path, label):
    with open(path, "rb") as f:
        raw = f.read()
    svg = repair_svg_bytes(raw)
    status = "ok"
    if svg is None:
        # last-ditch: try raw bytes directly (maybe it was fine, repair just failed to detect)
        svg = raw
        status = "unrepaired-raw"
    try:
        norm = normalize_to_black(svg)
        png = render_png(norm)
        h = to_phash(png)
        return {"path": path, "label": label, "status": status, "hash": str(h), "png": png}
    except Exception as e:
        return {"path": path, "label": label, "status": f"FAILED: {e}", "hash": None, "png": None}

if __name__ == "__main__":
    import sys
    results = []
    for base, label in [
        ("/sessions/epic-loving-franklin/icons/wrapper-icons/wrapper-icons", "wrapper"),
        ("/sessions/epic-loving-franklin/icons/inline-svgs/inline-svgs", "inline"),
    ]:
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".svg"):
                continue
            r = process_file(os.path.join(base, fn), label)
            results.append(r)

    fails = [r for r in results if r["hash"] is None]
    unrepaired_ok = [r for r in results if r["status"] == "unrepaired-raw"]
    print(f"Total: {len(results)}  Rendered OK: {len(results)-len(fails)}  Hard fails: {len(fails)}")
    print(f"(of which used lxml-recovery repair: {sum(1 for r in results if r['status']=='ok') } straightforward, "
          f"{len(unrepaired_ok)} fell back to raw-unrepaired attempt)")
    for r in fails:
        print("FAIL:", r["path"], r["status"])
