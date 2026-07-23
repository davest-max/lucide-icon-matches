import os, json, re
import cairosvg
from PIL import Image
import imagehash
import io

LUCIDE_DIR = "/sessions/epic-loving-franklin/node_modules/lucide-static/icons"
TAGS_PATH = "/sessions/epic-loving-franklin/node_modules/lucide-static/tags.json"

with open(TAGS_PATH) as f:
    tags = json.load(f)

def render_lucide(name):
    path = os.path.join(LUCIDE_DIR, name + ".svg")
    with open(path, "rb") as f:
        s = f.read().decode("utf-8")
    s = s.replace("currentColor", "#000000")
    # lucide default stroke-width is 2 on a 24x24 canvas; keep as-is
    png = cairosvg.svg2png(bytestring=s.encode("utf-8"), output_width=128, output_height=128,
                            background_color="white")
    return png

index = {}
names = sorted(fn[:-4] for fn in os.listdir(LUCIDE_DIR) if fn.endswith(".svg"))
print("Total lucide icons:", len(names))

for i, name in enumerate(names):
    try:
        png = render_lucide(name)
        h = imagehash.phash(Image.open(io.BytesIO(png)).convert("L"), hash_size=8)
    except Exception as e:
        print("FAIL", name, e)
        continue
    name_tokens = set(name.split("-"))
    tag_list = tags.get(name, [])
    tag_tokens = set()
    for t in tag_list:
        tag_tokens.update(t.lower().split())
    index[name] = {
        "hash": str(h),
        "name_tokens": sorted(name_tokens),
        "tag_tokens": sorted(tag_tokens),
    }
    if i % 300 == 0:
        print(i, name)

with open("/sessions/epic-loving-franklin/work/lucide_index.json", "w") as f:
    json.dump(index, f)
print("done, total indexed:", len(index))
