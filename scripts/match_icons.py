import os, sys, json, re, io
sys.path.insert(0, "/sessions/epic-loving-franklin/work")
from repair_and_render import process_file
import numpy as np
from PIL import Image
import cv2

LUCIDE_INDEX_PATH = "/sessions/epic-loving-franklin/work/lucide_index.json"
CANON_PATH = "/sessions/epic-loving-franklin/node_modules/lucide-static/icon-nodes.json"
MASKS_PATH = "/sessions/epic-loving-franklin/work/lucide_masks.npy"
MASK_NAMES_PATH = "/sessions/epic-loving-franklin/work/lucide_mask_names.json"
MASK_SIZE = 128
DILATE = 3

with open(LUCIDE_INDEX_PATH) as f:
    lucide_index = json.load(f)
with open(CANON_PATH) as f:
    canonical_names = set(json.load(f).keys())

# Shape-overlap visual signal: tight-cropped, centered, dilated silhouette masks
# compared by Jaccard/IoU. This replaced an earlier perceptual-hash (phash) and
# Hu-moment approach — both were empirically unreliable on this icon set (they
# ranked semantically-wrong candidates above obviously-correct ones in spot
# checks, e.g. preferring "kanban" over "headset" for an agent-headset icon).
# IoU on normalized silhouettes correlates with human judgment far better in
# the same spot checks, though it's still sensitive to rotation and stroke
# thickness — it is a heuristic, not ground truth.
lucide_masks = np.load(MASKS_PATH)  # shape (N, MASK_SIZE*MASK_SIZE) bool
with open(MASK_NAMES_PATH) as f:
    lucide_mask_names = json.load(f)
mask_name_to_row = {n: i for i, n in enumerate(lucide_mask_names)}

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

def iou_against_all_lucide(custom_mask_flat):
    """Vectorized IoU of one custom mask against every lucide mask at once."""
    inter = np.logical_and(lucide_masks, custom_mask_flat).sum(axis=1)
    union = np.logical_or(lucide_masks, custom_mask_flat).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = np.where(union > 0, inter / union, 0.0)
    return iou  # shape (N,), aligned with lucide_mask_names

# "agent" is a homonym trap: in this CX product it always means "customer
# service agent" (a person), but Lucide tags "hat-glasses" (a spy disguise)
# with "agent" (as in secret agent). Strip it from tag-matching so it doesn't
# become the default false-positive winner for every ccf-agent-*-icon file.
TAG_BLOCKLIST = {"agent"}
for name, d in lucide_index.items():
    d["tag_tokens"] = [t for t in d["tag_tokens"] if t not in TAG_BLOCKLIST]

# Matched as *whole tokens* against the tokenized filename (never raw substring —
# "line" as a substring check would wrongly flag "outline"/"timeline"/"baseline").
BRAND_TOKEN_KEYWORDS = {
    "facebook": "Facebook", "twitter": "Twitter/X", "linkedin": "LinkedIn",
    "instagram": "Instagram", "whatsapp": "WhatsApp", "telegram": "Telegram",
    "slack": "Slack", "teams": "Microsoft Teams", "msteams": "Microsoft Teams", "wechat": "WeChat",
    "line": "LINE", "viber": "Viber", "messenger": "Messenger", "youtube": "YouTube",
    "tiktok": "TikTok", "skype": "Skype", "kakao": "KakaoTalk", "google": "Google", "apple": "Apple",
    "wickr": "Wickr", "amazon": "Amazon", "yelp": "Yelp", "chat": None,  # placeholder, unused as brand alone
}
# drop the placeholder
BRAND_TOKEN_KEYWORDS.pop("chat")
# multi-token brand phrases (checked against the joined token string)
BRAND_PHRASE_KEYWORDS = {
    "apple-chat": "Apple Business Chat", "google-places": "Google (Places)",
}

STOPWORDS = {"icon", "icons", "name", "ccf", "cxagent"}

# Domain-specific shorthand used throughout this CX/CCaaS codebase.
ABBR = {
    "ib": "inbound", "ob": "outbound", "ibcall": "inbound call", "obcall": "outbound call",
    "acd": "automatic call distribution", "ivr": "interactive voice response",
    "sms": "sms text message", "mms": "mms text message", "wem": "workforce engagement management",
    "qm": "quality management", "vm": "voicemail", "ccf": "", "eta": "estimated time",
}

def camel_to_snake(s):
    # Only split genuine camelCase boundaries (lower/digit -> Upper). Leaves ALL_CAPS
    # and ALLCAPS runs (e.g. "IBCALL", "PERMISSION_DENIED") intact instead of
    # shredding them into single letters.
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', s)
    return s.lower()

def expand_abbr(tok):
    key = tok.lower()
    if key in ABBR:
        return ABBR[key].split()
    return [tok]

def clean_tokens(raw_name):
    """Return (tokens, category_hint, variant_suffix, brand) from a raw filename stem."""
    stem = raw_name
    category = None
    if "." in stem:
        parts = stem.split(".")
        category = parts[0]
        stem = parts[-1]
    # detect trailing _<number> variant e.g. REPLY_3
    variant = None
    m = re.match(r'^(.*)_(\d+)$', stem)
    if m:
        stem = m.group(1)
        variant = m.group(2)
    # strip prefixes
    stem2 = re.sub(r'^ccf-', '', stem)
    stem2 = camel_to_snake(stem2)
    stem2 = stem2.replace("-", "_")
    raw_tokens = [t for t in re.split(r'[_\s]+', stem2) if t]
    tokens = []
    for t in raw_tokens:
        if t.lower() in STOPWORDS:
            continue
        tokens.extend(w for w in expand_abbr(t) if w)
    tokens = [t.lower() for t in tokens if len(t) >= 2]  # drop stray single letters

    # brand detection: whole-token match only (never raw substring — avoids
    # "outline"/"timeline" false-hitting on "line").
    brand = None
    joined_tok_str = "-".join(tokens)
    if joined_tok_str in BRAND_PHRASE_KEYWORDS:
        brand = BRAND_PHRASE_KEYWORDS[joined_tok_str]
    else:
        for tok in tokens:
            if tok in BRAND_TOKEN_KEYWORDS:
                brand = BRAND_TOKEN_KEYWORDS[tok]
                break
    # custom in-house app logo (not a Lucide-replaceable third-party brand, but
    # still "no equivalent" — flag distinctly)
    if brand is None and "logo" in tokens and ("cxagent" in stem.lower() or "cxone" in stem.lower()):
        brand = "App logo (custom brand mark)"
    cat_tokens = []
    if category:
        cat_clean = camel_to_snake(category).replace("-", "_")
        craw = [t for t in re.split(r'[_\s]+', cat_clean) if t]
        for t in craw:
            if t.lower() in STOPWORDS:
                continue
            cat_tokens.extend(w for w in expand_abbr(t) if w)
        cat_tokens = [t.lower() for t in cat_tokens if len(t) >= 2]
    return tokens, cat_tokens, variant, brand

def _word_fuzzy_overlap(set_a, set_b, min_len=4):
    """Whole-token overlap, plus a conservative fuzzy pass: a token from one set
    matches a token from the other only if one *whole word* starts-with/ends-with
    the other and both are long enough (>=min_len) to avoid short-token noise
    (e.g. 'back' must not match inside 'backpack' via naive substring, but
    'assign' should still catch 'assignment')."""
    exact = set_a & set_b
    fuzzy = set()
    for a in set_a:
        if a in exact or len(a) < min_len:
            continue
        for b in set_b:
            if b in exact or len(b) < min_len:
                continue
            if a.startswith(b) or b.startswith(a):
                fuzzy.add((a, b))
                break
    return exact, fuzzy

def name_score(custom_tokens, cat_tokens, lucide_name, lucide_d):
    lname_tokens = set(lucide_d["name_tokens"])
    ltag_tokens = set(lucide_d["tag_tokens"])
    ctoks = set(custom_tokens)
    if not ctoks:
        return 0.0, ""
    joined_custom = "-".join(sorted(custom_tokens))
    joined_lucide = "-".join(sorted(lname_tokens))
    # exact name match (token-set equality, order independent)
    if ctoks == lname_tokens:
        return 1.0, "exact-tokens"
    if joined_custom == joined_lucide:
        return 1.0, "exact-tokens"
    # merged-word match: custom tokens concatenated with no separator equal the
    # lucide name with its hyphens removed (e.g. "logout" == "log"+"out" for "log-out")
    if "".join(custom_tokens) == lucide_name.replace("-", ""):
        return 0.95, "merged-word-exact"

    exact_name, fuzzy_name = _word_fuzzy_overlap(ctoks, lname_tokens)
    exact_tag, fuzzy_tag = _word_fuzzy_overlap(ctoks, ltag_tokens)

    score = 0.0
    reason = ""
    # full coverage of custom tokens by lucide name tokens (all words accounted for)
    if exact_name and exact_name == ctoks:
        extra = len(lname_tokens) - len(exact_name)
        score = max(0.75, 0.92 - 0.03 * extra)
        reason = "all-tokens-in-name:" + ",".join(sorted(exact_name))
    elif exact_name:
        coverage = len(exact_name) / len(ctoks)
        score = max(score, 0.45 + 0.35 * coverage)
        reason = "name-token:" + ",".join(sorted(exact_name))
    elif fuzzy_name:
        score = max(score, 0.55)
        reason = "name-fuzzy:" + ",".join(f"{a}~{b}" for a, b in fuzzy_name)
    if exact_tag:
        coverage = len(exact_tag) / len(ctoks)
        # A strong single-word tag hit (e.g. custom "attachment-preview" -> lucide
        # "eye" tagged "preview") shouldn't be capped low just because a generic
        # structural word like "attachment" didn't also match — weight the mere
        # presence of a real tag hit heavily, coverage as a smaller bonus on top.
        tag_score = 0.4 + 0.3 * coverage
        if tag_score > score:
            score = tag_score
            reason = "tag:" + ",".join(sorted(exact_tag))
    elif fuzzy_tag and score < 0.35:
        score = max(score, 0.3)
        reason = "tag-fuzzy:" + ",".join(f"{a}~{b}" for a, b in fuzzy_tag)
    # category tokens as weak secondary signal only (never overrides a real hit)
    if cat_tokens and score < 0.4:
        cat_overlap = set(cat_tokens) & (lname_tokens | ltag_tokens)
        cat_overlap = {t for t in cat_overlap if len(t) >= 4}
        if cat_overlap:
            score = max(score, 0.2 + 0.05 * len(cat_overlap))
            reason = (reason + "+cat:" if reason else "cat:") + ",".join(sorted(cat_overlap))
    return min(score, 0.96), reason

# Small curated overrides for generic single-word UI actions where Lucide's
# obvious canonical icon doesn't share the word in its name/tags strongly enough
# to win algorithmically, but visual inspection of the source icon confirms the
# match beyond doubt (e.g. our "close" icon renders as a plain X, not a panel widget).
CURATED_OVERRIDES = {
    ("close",): "x",
    ("back",): "chevron-left",
    ("help",): "circle-help",
}

def best_matches(raw_name, iou_vec, top_n=3):
    tokens, cat_tokens, variant, brand = clean_tokens(raw_name)
    override_key = tuple(sorted(tokens))

    def vs_for(lname):
        row = mask_name_to_row.get(lname)
        return float(iou_vec[row]) if row is not None and iou_vec is not None else 0.0

    if override_key in CURATED_OVERRIDES:
        lname = CURATED_OVERRIDES[override_key]
        vs = vs_for(lname)
        top = [(0.97, 0.97, vs, lname, "curated-override", lname in canonical_names)]
        rest = []
        for n2, d2 in lucide_index.items():
            if n2 == lname:
                continue
            ns2, reason2 = name_score(tokens, cat_tokens, n2, d2)
            vs2 = vs_for(n2)
            rest.append((0.6*ns2+0.4*vs2, ns2, vs2, n2, reason2, n2 in canonical_names))
        rest.sort(key=lambda x: (-x[0], not x[5]))
        top += rest[:top_n-1]
        return tokens, cat_tokens, variant, brand, top
    scored = []
    for lname, d in lucide_index.items():
        ns, reason = name_score(tokens, cat_tokens, lname, d)
        vs = vs_for(lname)
        combined = 0.6 * ns + 0.4 * vs
        scored.append((combined, ns, vs, lname, reason, lname in canonical_names))
    scored.sort(key=lambda x: (-x[0], not x[5]))
    return tokens, cat_tokens, variant, brand, scored[:top_n]

def confidence_tier(ns, vs, brand):
    if brand:
        return "NONE"
    # A pure shape coincidence (zero name/tag signal at all) still gets it wrong
    # too often to call HIGH, even at a strong IoU score (spot-checked: ~40% of
    # these were clearly incorrect despite high shape similarity, e.g. a
    # checkmark-in-circle matching "circle-chevron-down" on outer-ring shape
    # alone). Require at least some name/tag corroboration for HIGH.
    if ns >= 0.85 or (vs >= 0.75 and ns > 0):
        return "HIGH"
    if ns >= 0.5 or vs >= 0.55:
        return "MEDIUM"
    return "LOW"

def main():
    results = []
    for base, label in [
        ("/sessions/epic-loving-franklin/icons/wrapper-icons/wrapper-icons", "wrapper"),
        ("/sessions/epic-loving-franklin/icons/inline-svgs/inline-svgs", "inline"),
    ]:
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".svg"):
                continue
            raw_name = fn[:-4]
            r = process_file(os.path.join(base, fn), label)
            iou_vec = None
            if r["png"]:
                cmask = tight_mask(r["png"]).flatten()
                iou_vec = iou_against_all_lucide(cmask)
            tokens, cat_tokens, variant, brand, top = best_matches(raw_name, iou_vec, top_n=3)
            top1 = top[0]
            tier = confidence_tier(top1[1], top1[2], brand)
            results.append({
                "file": fn,
                "label": label,
                "raw_name": raw_name,
                "tokens": tokens,
                "category_tokens": cat_tokens,
                "variant": variant,
                "brand": brand,
                "top_matches": [
                    {"lucide": t[3], "combined": round(t[0],3), "name_score": round(t[1],3),
                     "visual_score": round(t[2],3), "reason": t[4], "canonical": t[5]}
                    for t in top
                ],
                "tier": tier,
                "render_status": r["status"],
            })
    with open("/sessions/epic-loving-franklin/work/match_results.json", "w") as f:
        json.dump(results, f, indent=1)
    # summary
    from collections import Counter
    c = Counter(r["tier"] for r in results)
    print("Tier counts:", dict(c))
    print("Total:", len(results))

if __name__ == "__main__":
    main()
