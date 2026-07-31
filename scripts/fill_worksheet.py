import csv, json, os, re, shutil, sys
from bs4 import BeautifulSoup
sys.path.insert(0, "/sessions/epic-loving-franklin/work")
from repair_and_render import repair_svg_bytes

SRC_HTML = "/sessions/epic-loving-franklin/mnt/uploads/index.html"
RESULTS = "/sessions/epic-loving-franklin/work/match_results.json"
# Dave's exported "Download CSV for devs" file, if he's shared one — when present,
# its final match / confidence for each icon becomes the new published baseline,
# so his review work survives every subsequent rebuild instead of being wiped out.
REVIEWED_CSV = "/sessions/epic-loving-franklin/work/reviewed_overrides.csv"

def load_reviewed_overrides(path):
    if not path or not os.path.exists(path):
        return {}
    overrides = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            source = (row.get("source") or "").strip()
            ccf = (row.get("ccf_icon_file") or "").strip()
            if not ccf:
                continue
            tier = (row.get("confidence") or "").strip().upper()
            if tier not in ("HIGH", "MEDIUM", "LOW", "NONE", "CUSTOM"):
                continue
            lucide = (row.get("final_lucide_match") or "").strip() or None
            overrides[(source, ccf)] = {"tier": tier, "lucide": lucide}
    print(f"Loaded {len(overrides)} reviewed overrides from {path}")
    return overrides
LUCIDE_SVG_DIR = "/sessions/epic-loving-franklin/node_modules/lucide-static/icons"
LUCIDE_TAGS_PATH = "/sessions/epic-loving-franklin/node_modules/lucide-static/tags.json"
SRC_WRAPPER_DIR = "/sessions/epic-loving-franklin/icons/wrapper-icons/wrapper-icons"
SRC_INLINE_DIR = "/sessions/epic-loving-franklin/icons/inline-svgs/inline-svgs"

OUT_DIR = "/sessions/epic-loving-franklin/work/package"
OUT_HTML = os.path.join(OUT_DIR, "index.html")
OUT_LUCIDE_DIR = os.path.join(OUT_DIR, "lucide-icons")
OUT_WRAPPER_DIR = os.path.join(OUT_DIR, "wrapper-icons")
OUT_INLINE_DIR = os.path.join(OUT_DIR, "inline-svgs")

with open(RESULTS) as f:
    results = json.load(f)

by_key = {}
for r in results:
    stem = r["raw_name"]
    by_key[(r["label"], stem)] = r

TIER_COLORS = {
    "HIGH": ("#e6f4ea", "#1e7e34", "High confidence"),
    "MEDIUM": ("#fff8e1", "#8a6d00", "Medium — please verify"),
    "LOW": ("#fdeaea", "#a13a3a", "Low — best effort, review"),
    "NONE": ("#eceff1", "#455a64", "No Lucide equivalent"),
    "CUSTOM": ("#f3ecfa", "#6b3fa0", "Custom icon"),
}

def label_for_src(src):
    if src.startswith("wrapper-icons/"):
        return "wrapper", src[len("wrapper-icons/"):-4]
    if src.startswith("inline-svgs/"):
        return "inline", src[len("inline-svgs/"):-4]
    return None, None

def export_repaired_source_icons():
    """Write out browser-safe copies of every source SVG (JSX artifacts /
    malformed markup repaired, original colors kept) so the worksheet's own
    preview thumbnails actually render in a real browser instead of showing
    the broken-image glyph."""
    os.makedirs(OUT_WRAPPER_DIR, exist_ok=True)
    os.makedirs(OUT_INLINE_DIR, exist_ok=True)
    n_repaired, n_raw, n_total = 0, 0, 0
    for src_dir, out_dir in [(SRC_WRAPPER_DIR, OUT_WRAPPER_DIR), (SRC_INLINE_DIR, OUT_INLINE_DIR)]:
        for fn in os.listdir(src_dir):
            if not fn.endswith(".svg"):
                continue
            n_total += 1
            with open(os.path.join(src_dir, fn), "rb") as f:
                raw = f.read()
            fixed = repair_svg_bytes(raw)
            out_path = os.path.join(out_dir, fn)
            if fixed is not None:
                with open(out_path, "wb") as f:
                    f.write(fixed)
                n_repaired += 1
            else:
                with open(out_path, "wb") as f:
                    f.write(raw)
                n_raw += 1
    print(f"Source icons exported: {n_total} (repaired: {n_repaired}, copied as-is: {n_raw})")

def copy_all_lucide_icons_and_build_index():
    """Copy the entire Lucide icon set (not just the ones already used as
    suggestions) so the picker can search/select any of them, and build a
    compact client-side search index (name + tags) embedded in the page."""
    os.makedirs(OUT_LUCIDE_DIR, exist_ok=True)
    with open(LUCIDE_TAGS_PATH) as f:
        tags = json.load(f)
    names = sorted(fn[:-4] for fn in os.listdir(LUCIDE_SVG_DIR) if fn.endswith(".svg"))
    index = []
    for name in names:
        shutil.copy(os.path.join(LUCIDE_SVG_DIR, name + ".svg"), os.path.join(OUT_LUCIDE_DIR, name + ".svg"))
        search_text = name.replace("-", " ") + " " + " ".join(tags.get(name, []))
        index.append([name, search_text.lower()])
    print(f"Copied full Lucide set: {len(names)} icons")
    return index

TIER_OPTIONS = [("HIGH", "High"), ("MEDIUM", "Medium"), ("LOW", "Low"), ("NONE", "No match"), ("CUSTOM", "Custom")]

def build_tier_select(soup, current_tier):
    sel = soup.new_tag("select", **{"class": "tier-override-select", "onchange": "setTierOverride(this)"})
    sel["style"] = ("font-size:12px;padding:6px 8px;border-radius:6px;border:1px solid #c3c5c9;"
                     "background:#fff;margin-top:6px;width:100%;cursor:pointer;")
    for val, label in TIER_OPTIONS:
        opt = soup.new_tag("option", value=val)
        opt.string = label
        if val == current_tier:
            opt["selected"] = "selected"
        sel.append(opt)
    return sel

def build_change_icon_button(soup):
    btn = soup.new_tag("button", **{"class": "change-icon-btn", "type": "button",
                                     "onclick": "openPicker(this)"})
    btn["style"] = ("font-size:12px;padding:7px 10px;border-radius:6px;border:1px solid #166cca;"
                     "background:#fff;color:#166cca;cursor:pointer;margin-top:6px;width:100%;font-weight:600;")
    btn.string = "Search Lucide icons…"
    return btn

def build_suggestion_label(soup):
    label = soup.new_tag("div")
    label["style"] = "font-size:10.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:#8a97a3;margin-bottom:4px;"
    label.string = "Suggested Lucide match"
    return label

def build_icon_row(soup, lucide_name, visible):
    """The img+name row that represents the current Lucide suggestion. Always
    present (even for 'No match' cells, just hidden/empty) so the JS picker
    never has to special-case building this structure — it only ever updates
    these two elements, never touches the ccf source icon above."""
    row = soup.new_tag("div", **{"class": "suggestion-row",
                                  "style": "display:flex;align-items:center;gap:8px;" + ("" if visible else "display:none;")})
    img = soup.new_tag("img", **{"class": "suggestion-img"},
                        src=(f"lucide-icons/{lucide_name}.svg" if lucide_name else ""),
                        style="width:30px;height:30px;flex:0 0 auto;")
    row.append(img)
    text = soup.new_tag("div", **{"style": "font-size:13.5px;line-height:1.3;"})
    name_span = soup.new_tag("span", **{"class": "suggestion-name", "style": "font-weight:600;"})
    name_span.string = lucide_name or ""
    text.append(name_span)
    row.append(text)
    return row

def build_suggestion_html(soup, r, override=None):
    """override, when given, is {'tier': 'HIGH'/'MEDIUM'/'LOW'/'NONE'/'CUSTOM', 'lucide': name-or-None}
    reflecting Dave's own reviewed CSV — takes the place of the algorithmic tier/match for this cell,
    becoming the new published baseline instead of an in-browser-only override."""
    wrap = soup.new_tag("div", **{"class": "lucide-match"})
    if override:
        tier = override["tier"]
        # Custom always means "keep the existing custom icon" — show the plain
        # placeholder/note treatment even if a Lucide candidate was noted during
        # review, so every Custom-tagged tile looks and reads the same way.
        lucide_name = None if tier == "CUSTOM" else override["lucide"]
    else:
        tier = r["tier"]
        lucide_name = None if tier == "NONE" else r["top_matches"][0]["lucide"]
    bg, fg, tier_label = TIER_COLORS[tier]
    wrap["style"] = f"background:{bg};border-radius:6px;padding:6px;margin-top:4px;width:100%;box-sizing:border-box;"
    wrap.append(build_suggestion_label(soup))

    if not lucide_name:
        wrap.append(build_icon_row(soup, None, visible=False))
        badge = soup.new_tag("div", **{"class": "tier-badge"})
        badge["style"] = f"color:{fg};font-size:12.5px;font-weight:600;"
        if tier == "NONE" and not override:
            badge.string = f"No Lucide equivalent — {r['brand']}"
        else:
            badge.string = tier_label
        wrap.append(badge)
        note = soup.new_tag("div", **{"class": "icon-note"})
        note["style"] = "font-size:12px;color:#555;margin-top:3px;"
        note.string = "Keep existing custom icon — or search below."
        wrap.append(note)
        wrap.append(build_change_icon_button(soup))
        wrap.append(build_tier_select(soup, tier))
        return wrap, None

    wrap.append(build_icon_row(soup, lucide_name, visible=True))

    badge = soup.new_tag("div", **{"class": "tier-badge"})
    badge["style"] = f"color:{fg};font-size:12px;font-weight:600;margin-top:4px;"
    badge.string = tier_label
    wrap.append(badge)

    if not override and len(r["top_matches"]) > 1:
        alt = r["top_matches"][1]["lucide"]
        alt_div = soup.new_tag("div", **{"class": "icon-note"})
        alt_div["style"] = "font-size:11.5px;color:#777;margin-top:2px;"
        alt_div.string = f"alt: {alt}"
        wrap.append(alt_div)

    wrap.append(build_change_icon_button(soup))
    wrap.append(build_tier_select(soup, tier))

    return wrap, lucide_name

CHIP_STYLE_BLOCK = """
<style>
  /* --- larger tile content: overrides the base worksheet stylesheet above --- */
  .controls input { font-size:15px !important; padding:10px 12px !important; }
  .grid { grid-template-columns:repeat(auto-fill,minmax(224px,1fr)) !important; gap:16px !important; }
  .cell { padding:16px !important; gap:9px !important; }
  .preview { width:56px !important; height:56px !important; }
  .preview img { width:36px !important; height:36px !important; }
  .name { font-size:13.5px !important; }
  .replace { font-size:13px !important; min-height:28px !important; padding:6px 8px !important; }

  .tier-chip {
    font-size: 13.5px; font-weight: 600; padding: 8px 18px; border-radius: 999px;
    cursor: pointer; border: 1.5px solid; background: #fff; transition: all .1s ease;
    user-select: none;
  }
  .tier-chip[data-tier="HIGH"]   { border-color:#1e7e34; color:#1e7e34; }
  .tier-chip[data-tier="HIGH"].active   { background:#1e7e34; color:#fff; }
  .tier-chip[data-tier="MEDIUM"] { border-color:#8a6d00; color:#8a6d00; }
  .tier-chip[data-tier="MEDIUM"].active { background:#8a6d00; color:#fff; }
  .tier-chip[data-tier="LOW"]    { border-color:#a13a3a; color:#a13a3a; }
  .tier-chip[data-tier="LOW"].active    { background:#a13a3a; color:#fff; }
  .tier-chip[data-tier="NONE"]   { border-color:#455a64; color:#455a64; }
  .tier-chip[data-tier="NONE"].active   { background:#455a64; color:#fff; }
  .tier-chip[data-tier="CUSTOM"]   { border-color:#6b3fa0; color:#6b3fa0; }
  .tier-chip[data-tier="CUSTOM"].active   { background:#6b3fa0; color:#fff; }
  .tier-chip:not(.active) { opacity: .55; }
  .tier-badge.manual-override::after { content: " (manual)"; font-weight: 400; font-style: italic; opacity: .8; }
  .tier-override-select:focus { outline: 2px solid #166cca; }
  .icon-changed-flag { font-size: 11px; font-style: italic; color: #166cca; margin-top: 4px; }
  .change-icon-btn:hover { background: #eaf3fb; }

  #icon-picker-overlay {
    display: none; position: fixed; inset: 0; background: rgba(20,30,40,.45);
    z-index: 1000; align-items: flex-start; justify-content: center; padding: 40px 20px;
  }
  #icon-picker-overlay.open { display: flex; }
  #icon-picker-modal {
    background: #fff; border-radius: 10px; width: 100%; max-width: 820px; max-height: 82vh;
    display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,.25);
  }
  #icon-picker-header {
    padding: 16px 20px; border-bottom: 1px solid #e4e7eb; display: flex; align-items: center; gap: 10px;
  }
  #icon-picker-header input {
    flex: 1; padding: 11px 12px; border: 1px solid #c3c5c9; border-radius: 6px; font-size: 15px;
  }
  #icon-picker-header .current-preview { display:flex; align-items:center; gap:6px; font-size:13px; color:#5d6a79; }
  #icon-picker-close {
    border: none; background: none; font-size: 24px; cursor: pointer; color: #5d6a79; line-height: 1;
    padding: 6px 10px;
  }
  #icon-picker-results {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 10px;
    padding: 16px 20px; overflow-y: auto;
  }
  .picker-item {
    border: 1px solid #e4e7eb; border-radius: 8px; padding: 11px 6px; display: flex; flex-direction: column;
    align-items: center; gap: 6px; cursor: pointer; background: #fff; text-align: center;
  }
  .picker-item:hover { background: #eaf3fb; border-color: #166cca; }
  .picker-item img { width: 32px; height: 32px; }
  .picker-item span { font-size: 11px; color: #2a2d32; word-break: break-all; line-height: 1.25; }
  #icon-picker-status { padding: 8px 20px 14px; font-size: 12.5px; color: #5d6a79; }
</style>
"""

PICKER_MODAL_HTML = """
<div id="icon-picker-overlay" onclick="if(event.target===this) closePicker()">
  <div id="icon-picker-modal">
    <div id="icon-picker-header">
      <span class="current-preview">Choosing Lucide match for ccf icon: <b id="picker-target-name">—</b></span>
      <input id="picker-search" type="text" placeholder="Search Lucide icons (e.g. phone, arrow, calendar)…" oninput="renderPickerResults(this.value)"/>
      <button id="icon-picker-close" onclick="closePicker()">✕</button>
    </div>
    <div id="icon-picker-results"></div>
    <div id="icon-picker-status"></div>
  </div>
</div>
"""

TIER_FILTER_UI = """
<div class="tier-filters" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px;">
  <span style="font-size:13.5px;color:#5d6a79;">Show confidence:</span>
  <button class="tier-chip active" data-tier="HIGH" onclick="toggleChip(this)">High</button>
  <button class="tier-chip active" data-tier="MEDIUM" onclick="toggleChip(this)">Medium</button>
  <button class="tier-chip active" data-tier="LOW" onclick="toggleChip(this)">Low</button>
  <button class="tier-chip active" data-tier="NONE" onclick="toggleChip(this)">No match</button>
  <button class="tier-chip active" data-tier="CUSTOM" onclick="toggleChip(this)">Custom</button>
  <span id="tier-count" style="font-size:12.5px;color:#5d6a79;margin-left:6px;"></span>
  <button onclick="resetTierOverridesOnly()" style="font-size:13px;padding:8px 14px;border:1px solid #c3c5c9;border-radius:6px;background:#fff;cursor:pointer;margin-left:auto;">Fix confidence levels</button>
  <button onclick="resetAllOverrides()" style="font-size:13px;padding:8px 14px;border:1px solid #c3c5c9;border-radius:6px;background:#fff;cursor:pointer;">Reset icon + confidence overrides</button>
</div>
<div class="export-row" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px;">
  <span style="font-size:13.5px;color:#5d6a79;">Share your work:</span>
  <button onclick="exportCsv()" style="font-size:14px;padding:8px 16px;border:1px solid #166cca;border-radius:6px;background:#166cca;color:#fff;cursor:pointer;font-weight:600;">Download CSV for devs</button>
  <button onclick="exportHtml()" style="font-size:14px;padding:8px 16px;border:1px solid #166cca;border-radius:6px;background:#fff;color:#166cca;cursor:pointer;font-weight:600;">Download updated worksheet (.html)</button>
  <span style="font-size:12px;color:#8a97a3;">CSV = one row per icon with the final match + confidence. HTML = this whole page, edits baked in, to send or reopen anywhere.</span>
</div>
"""

TIER_LABEL_TEXT = {
    "HIGH": "High confidence",
    "MEDIUM": "Medium — please verify",
    "LOW": "Low — best effort, review",
    "NONE": "No Lucide equivalent",
    "CUSTOM": "Custom icon",
}
TIER_COLOR_TEXT = {"HIGH": "#1e7e34", "MEDIUM": "#8a6d00", "LOW": "#a13a3a", "NONE": "#455a64", "CUSTOM": "#6b3fa0"}
TIER_BG_TEXT = {"HIGH": "#e6f4ea", "MEDIUM": "#fff8e1", "LOW": "#fdeaea", "NONE": "#eceff1", "CUSTOM": "#f3ecfa"}

NEW_FILTER_SCRIPT = f"""
const TIER_LABELS = {json.dumps(TIER_LABEL_TEXT)};
const TIER_FG = {json.dumps(TIER_COLOR_TEXT)};
const TIER_BG = {json.dumps(TIER_BG_TEXT)};
const OVERRIDE_PREFIX = 'iconTierOverride::';

function safeStorage(){{
  try {{ localStorage.setItem('__test__','1'); localStorage.removeItem('__test__'); return localStorage; }}
  catch(e) {{ return null; }}
}}
const STORE = safeStorage();

function currentQuery(){{ return (document.getElementById('q').value||'').toLowerCase(); }}
function toggleChip(el){{ el.classList.toggle('active'); applyFilters(); }}
function activeTiers(){{
  return Array.from(document.querySelectorAll('.tier-chip.active')).map(c=>c.getAttribute('data-tier'));
}}
function applyFilters(){{
  const q = currentQuery();
  const tiers = activeTiers();
  let shown = 0, total = 0;
  document.querySelectorAll('.cell').forEach(c=>{{
    total++;
    const n = c.querySelector('.name').textContent.toLowerCase();
    const t = c.getAttribute('data-tier');
    const match = n.includes(q) && tiers.includes(t);
    c.style.display = match ? '' : 'none';
    if (match) shown++;
  }});
  const countEl = document.getElementById('tier-count');
  if (countEl) countEl.textContent = shown + ' / ' + total + ' shown';
}}
function filter(v){{ applyFilters(); }}

function paintTier(cell, tier, isOverride){{
  cell.setAttribute('data-tier', tier);
  const wrap = cell.querySelector('.lucide-match');
  if (wrap) wrap.style.background = TIER_BG[tier];
  const badge = cell.querySelector('.tier-badge');
  if (badge){{
    badge.style.color = TIER_FG[tier];
    badge.textContent = tier === 'NONE' && badge.textContent.startsWith('No Lucide')
      ? badge.textContent  // keep the brand-specific "No Lucide equivalent — X" text as-is
      : TIER_LABELS[tier];
    badge.classList.toggle('manual-override', !!isOverride);
  }}
}}

function setTierOverride(selectEl){{
  const cell = selectEl.closest('.cell');
  const id = cell.getAttribute('data-id');
  const original = cell.getAttribute('data-original-tier');
  const newTier = selectEl.value;
  paintTier(cell, newTier, newTier !== original);
  if (STORE){{
    if (newTier === original) STORE.removeItem(OVERRIDE_PREFIX + id);
    else STORE.setItem(OVERRIDE_PREFIX + id, newTier);
  }}
  applyFilters();
}}

function resetTierOverridesOnly(){{
  // Restores each cell's confidence dropdown/badge back to its original
  // computed tier, clearing only stray confidence overrides (e.g. left over
  // from earlier testing). Icon picks (which Lucide match is shown) are
  // left completely untouched.
  document.querySelectorAll('.cell').forEach(cell=>{{
    const original = cell.getAttribute('data-original-tier');
    const id = cell.getAttribute('data-id');
    const hadOverride = STORE ? !!STORE.getItem(OVERRIDE_PREFIX + id) : false;
    const sel = cell.querySelector('.tier-override-select');
    const current = sel ? sel.value : original;
    if (hadOverride || current !== original) {{
      if (sel) sel.value = original;
      paintTier(cell, original, false);
      if (STORE) STORE.removeItem(OVERRIDE_PREFIX + id);
    }}
  }});
  applyFilters();
}}

function resetAllOverrides(){{
  document.querySelectorAll('.cell').forEach(cell=>{{
    const original = cell.getAttribute('data-original-tier');
    const sel = cell.querySelector('.tier-override-select');
    if (sel) sel.value = original;
    paintTier(cell, original, false);
    const id = cell.getAttribute('data-id');
    if (STORE) {{
      STORE.removeItem(OVERRIDE_PREFIX + id);
      STORE.removeItem(NAME_OVERRIDE_PREFIX + id);
    }}
    const originalIcon = cell.getAttribute('data-original-icon') || '';
    const replaceBox = cell.querySelector('.replace');
    const row = cell.querySelector('.suggestion-row');
    const flag = cell.querySelector('.icon-changed-flag');
    if (originalIcon){{
      applyIconChoice(cell, originalIcon, false);
    }} else {{
      // originally a NONE-tier / no-suggestion cell — revert to that state
      if (row) row.style.display = 'none';
      if (flag) flag.remove();
      if (replaceBox) replaceBox.textContent = '';
    }}
  }});
  applyFilters();
}}

function applyStoredOverrides(){{
  if (!STORE) return;
  document.querySelectorAll('.cell').forEach(cell=>{{
    const id = cell.getAttribute('data-id');
    const original = cell.getAttribute('data-original-tier');
    const saved = STORE.getItem(OVERRIDE_PREFIX + id);
    if (saved){{
      const sel = cell.querySelector('.tier-override-select');
      if (sel) sel.value = saved;
      // Only flag as a manual override if it actually differs from the
      // published baseline — otherwise a leftover browser entry from before
      // a reviewed export was merged in would falsely tag it "(manual)".
      paintTier(cell, saved, saved !== original);
      if (saved === original) STORE.removeItem(OVERRIDE_PREFIX + id);
    }}
  }});
}}

const NAME_OVERRIDE_PREFIX = 'iconNameOverride::';
let pickerTargetCell = null;
const MAX_PICKER_RESULTS = 200;

function openPicker(btnEl){{
  pickerTargetCell = btnEl.closest('.cell');
  const nameEl = pickerTargetCell.querySelector('.name');
  document.getElementById('picker-target-name').textContent = nameEl ? nameEl.textContent : '';
  document.getElementById('picker-search').value = '';
  document.getElementById('icon-picker-overlay').classList.add('open');
  renderPickerResults('');
  document.getElementById('picker-search').focus();
}}
function closePicker(){{
  document.getElementById('icon-picker-overlay').classList.remove('open');
  pickerTargetCell = null;
}}
function renderPickerResults(query){{
  const q = (query||'').trim().toLowerCase();
  const results = document.getElementById('icon-picker-results');
  const status = document.getElementById('icon-picker-status');
  results.innerHTML = '';
  const matches = LUCIDE_ICONS.filter(([name, text]) => q === '' || text.includes(q));
  const shown = matches.slice(0, MAX_PICKER_RESULTS);
  shown.forEach(([name]) => {{
    const item = document.createElement('div');
    item.className = 'picker-item';
    item.onclick = () => selectIcon(name);
    const img = document.createElement('img');
    img.src = 'lucide-icons/' + name + '.svg';
    img.loading = 'lazy';
    const label = document.createElement('span');
    label.textContent = name;
    item.appendChild(img);
    item.appendChild(label);
    results.appendChild(item);
  }});
  status.textContent = matches.length > MAX_PICKER_RESULTS
    ? `Showing first ${{MAX_PICKER_RESULTS}} of ${{matches.length}} matches — keep typing to narrow it down.`
    : `${{matches.length}} icon${{matches.length===1?'':'s'}}`;
}}

function applyIconChoice(cell, name, isOverride){{
  // Updates ONLY the suggested-Lucide-match elements. The ccf source icon at
  // the top of the cell (.preview img) is never touched by this function.
  const row = cell.querySelector('.suggestion-row');
  const img = cell.querySelector('.suggestion-img');
  const nameSpan = cell.querySelector('.suggestion-name');
  const replaceBox = cell.querySelector('.replace');
  if (row) row.style.display = 'flex';
  if (img) img.src = 'lucide-icons/' + name + '.svg';
  if (nameSpan) nameSpan.textContent = name;
  if (replaceBox) replaceBox.textContent = name;
  let flag = cell.querySelector('.icon-changed-flag');
  if (isOverride){{
    if (!flag){{
      flag = document.createElement('div');
      flag.className = 'icon-changed-flag';
      flag.textContent = 'Lucide match manually picked — set confidence below';
      cell.querySelector('.lucide-match').appendChild(flag);
    }}
  }} else if (flag) {{ flag.remove(); }}
}}

function selectIcon(name){{
  if (!pickerTargetCell) return;
  const id = pickerTargetCell.getAttribute('data-id');
  applyIconChoice(pickerTargetCell, name, true);
  if (STORE) STORE.setItem(NAME_OVERRIDE_PREFIX + id, name);
  closePicker();
}}

function applyStoredIconOverrides(){{
  if (!STORE) return;
  document.querySelectorAll('.cell').forEach(cell=>{{
    const id = cell.getAttribute('data-id');
    const saved = STORE.getItem(NAME_OVERRIDE_PREFIX + id);
    if (saved){{
      const originalIcon = cell.getAttribute('data-original-icon') || '';
      applyIconChoice(cell, saved, saved !== originalIcon);
      if (saved === originalIcon) STORE.removeItem(NAME_OVERRIDE_PREFIX + id);
    }}
  }});
}}

document.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') closePicker();
}});

function downloadBlob(content, filename, mimeType){{
  const blob = new Blob([content], {{ type: mimeType }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}}
function csvEscape(v){{
  v = (v == null) ? '' : String(v);
  return /[",\\n]/.test(v) ? '"' + v.replace(/"/g,'""') + '"' : v;
}}

function exportCsv(){{
  const rows = [[
    'ccf_icon_file','source','final_lucide_match','confidence',
    'confidence_manually_set','icon_manually_picked','note'
  ]];
  document.querySelectorAll('.cell').forEach(cell=>{{
    const id = cell.getAttribute('data-id') || '';
    const [source, ccfName] = id.includes(':') ? id.split(/:(.+)/) : ['', id];
    const tier = cell.getAttribute('data-tier') || '';
    const badge = cell.querySelector('.tier-badge');
    const badgeText = badge ? badge.textContent.replace(' (manual)','') : '';
    const isManualTier = badge ? badge.classList.contains('manual-override') : false;
    const isManualIcon = !!cell.querySelector('.icon-changed-flag');
    const replaceBox = cell.querySelector('.replace');
    const finalMatch = replaceBox ? replaceBox.textContent.trim() : '';
    const note = (tier === 'NONE' && !finalMatch) ? badgeText : '';
    rows.push([ccfName, source, finalMatch, tier, isManualTier ? 'yes':'no', isManualIcon ? 'yes':'no', note]);
  }});
  const csv = rows.map(r => r.map(csvEscape).join(',')).join('\\n');
  downloadBlob(csv, 'icon_lucide_matches.csv', 'text/csv');
}}

function exportHtml(){{
  const clone = document.documentElement.cloneNode(true);
  // close the picker overlay in the exported copy so it doesn't open pre-shown
  const overlay = clone.querySelector('#icon-picker-overlay');
  if (overlay) overlay.classList.remove('open');
  const searchBox = clone.querySelector('#q');
  if (searchBox) searchBox.value = '';
  const html = '<!doctype html>\\n' + clone.outerHTML;
  downloadBlob(html, 'icon_lucide_worksheet_updated.html', 'text/html');
}}

document.addEventListener('DOMContentLoaded', () => {{
  applyStoredIconOverrides();
  applyStoredOverrides();
  applyFilters();
}});
"""

def main():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_LUCIDE_DIR, exist_ok=True)

    export_repaired_source_icons()
    reviewed = load_reviewed_overrides(REVIEWED_CSV)

    with open(SRC_HTML, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    used_lucide = set()
    matched, unmatched = 0, 0
    reviewed_applied = 0
    tier_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0, "CUSTOM": 0}

    for cell in soup.select(".cell"):
        img = cell.select_one(".preview img")
        if not img:
            continue
        src = img.get("src", "")
        label, stem = label_for_src(src)
        r = by_key.get((label, stem))
        replace_div = cell.select_one(".replace")
        if not r:
            unmatched += 1
            continue
        matched += 1

        override = reviewed.get((label, stem))
        if override:
            reviewed_applied += 1
            eff_tier = override["tier"]
        else:
            eff_tier = r["tier"]

        cell["data-tier"] = eff_tier
        cell["data-original-tier"] = eff_tier
        cell["data-id"] = f"{r['label']}:{r['raw_name']}"
        cell["data-original-icon"] = ""
        tier_counts[eff_tier] += 1
        suggestion, lname = build_suggestion_html(soup, r, override=override)
        if lname:
            used_lucide.add(lname)
            replace_div.string = lname
            cell["data-original-icon"] = lname
        elif eff_tier == "CUSTOM":
            replace_div["data-ph"] = "Custom icon — keep as-is"
        else:
            replace_div["data-ph"] = f"No Lucide equivalent ({r['brand']}) — keep custom"
        replace_div.insert_after(suggestion)

    # header copy
    header_p = soup.select_one("header p")
    if header_p:
        header_p.string = (
            "AW-60964 · 352 icon-library icons + 52 inline (hardcoded) icons = 404 total. The "
            "ccf icon at the top of each box is fixed (that's the one being replaced) — below it "
            "is the suggested Lucide match (name + thumbnail + confidence). High/Medium = "
            "algorithmic name+shape match; Low = best-effort, please review; brand logos are "
            "flagged with no forced match. Click \"Search Lucide icons…\" to look through the "
            "full Lucide set and swap in a different match, then use the small dropdown to set "
            "its confidence level, or mark it \"Custom\" if it should stay a custom (non-Lucide) "
            "icon — that files it under the Custom Icons filter chip instead. Changes persist on "
            "reload. If a confidence "
            "level ever looks wrong, click \"Fix confidence levels\" to restore every dropdown to "
            "its correct computed value without losing your icon picks — or \"Reset icon + "
            "confidence overrides\" to undo everything. Use the confidence filter chips below. "
            "When you're done, "
            "use \"Download CSV for devs\" (a clean spreadsheet of ccf icon → final Lucide match) "
            "or \"Download updated worksheet\" (this whole page with your edits baked in) to "
            "share your work — edits made here only live in your browser until you download one "
            "of those."
        )

    # chip + picker stylesheet goes in <head>
    head = soup.select_one("head")
    if head:
        head.append(BeautifulSoup(CHIP_STYLE_BLOCK, "html.parser"))

    # insert tier-filter UI right after the existing search controls
    controls_div = soup.select_one(".controls")
    if controls_div:
        filter_soup = BeautifulSoup(TIER_FILTER_UI, "html.parser")
        controls_div.append(filter_soup)

    # picker modal, appended once at the end of <body>
    body = soup.select_one("body")
    if body:
        body.append(BeautifulSoup(PICKER_MODAL_HTML, "html.parser"))

    # build the full Lucide search index and copy every icon (so the picker
    # can offer any of them, not just the ones already used as suggestions)
    lucide_search_index = copy_all_lucide_icons_and_build_index()
    index_script = soup.new_tag("script")
    index_script.string = "const LUCIDE_ICONS = " + json.dumps(lucide_search_index) + ";"

    # replace the old inline filter script with the tier+name+picker aware one
    script_tag = soup.find("script")
    if script_tag:
        script_tag.insert_before(index_script)
        script_tag.string = NEW_FILTER_SCRIPT

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(str(soup))

    print(f"Matched cells: {matched}, unmatched (no lookup): {unmatched}, suggestions used: {len(used_lucide)}, reviewed overrides applied: {reviewed_applied}")
    print("Tier counts:", tier_counts)

if __name__ == "__main__":
    main()
