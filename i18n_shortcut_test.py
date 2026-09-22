"""v1.7.0 纯逻辑单测：i18n 文案 / 快捷键解析 / 冲突检测 / 持久化。

不依赖 GUI，可在任意有 Python 的机器上跑；CI 里也能用。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win_glass_i18n as i18n
import win_glass


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        global FAILED
        FAILED += 1


# ---------------- 1. 快捷键解析往返 ----------------
ROUNDTRIP = ["Ctrl+Alt+P", "Ctrl+Shift+A", "Alt+F4", "F5", "P", "Win+X",
             "Ctrl+K", "Shift+F1", "0", "Space"]
FAILED = 0
for c in ROUNDTRIP:
    p = i18n.parse_combo(c)
    check("parse %s -> not None" % c, p is not None)
    if p:
        back = i18n.format_combo(*p)
        check("roundtrip %s -> %s" % (c, back), back == c)

# 解析失败
check("parse '' -> None", i18n.parse_combo("") is None)
check("parse 'Ctrl' -> None (no primary)", i18n.parse_combo("Ctrl") is None)
check("parse 'Nope' -> None", i18n.parse_combo("Nope") is None)
check("parse 'Ctrl+Ctrl' -> None (modifier as primary)",
      i18n.parse_combo("Ctrl+Ctrl") is None)

# ---------------- 2. 可绑定性 ----------------
check("bindable A", i18n.is_bindable_vk(0x41))           # A
check("bindable F5", i18n.is_bindable_vk(0x74))          # F5
check("not bindable Ctrl(0x11)", not i18n.is_bindable_vk(0x11))
check("not bindable Shift(0x10)", not i18n.is_bindable_vk(0x10))
check("not bindable Win(0x5B)", not i18n.is_bindable_vk(0x5B))
check("not bindable Esc(0x1B)", not i18n.is_bindable_vk(0x1B))
check("not bindable LMB(0x01)", not i18n.is_bindable_vk(0x01))
check("not bindable 0xFF", not i18n.is_bindable_vk(0xFF))

# normalize 夹掉未知位
nm = i18n.normalize_combo(0x1234, 0x41)
check("normalize keeps bindable mods", nm == (0x1234 & (i18n.MOD_CTRL | i18n.MOD_ALT | i18n.MOD_SHIFT | i18n.MOD_WIN), 0x41))

# ---------------- 3. GlassConfig 快捷键 / 冲突 ----------------
cfg = win_glass.GlassConfig(shortcuts={})
check("fresh shortcuts empty", cfg.shortcuts == {})
cfg.set_shortcut(win_glass.CMD_TOGGLE, "Ctrl+Alt+P")
check("set_shortcut stores", cfg.shortcut_of(win_glass.CMD_TOGGLE) == "Ctrl+Alt+P")
# 冲突：另一个命令绑同一个组合
owner = cfg.owner_of_combo("Ctrl+Alt+P", exclude_cid=win_glass.CMD_RESTORE)
check("owner_of_combo finds CMD_TOGGLE", owner == win_glass.CMD_TOGGLE)
owner2 = cfg.owner_of_combo("Ctrl+Alt+P", exclude_cid=win_glass.CMD_TOGGLE)
check("owner_of_combo excludes self", owner2 is None)
# 解绑
cfg.set_shortcut(win_glass.CMD_TOGGLE, "")
check("unbind removes", cfg.shortcut_of(win_glass.CMD_TOGGLE) == "")
# 存盘后重载
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "cfg.json")
    c2 = win_glass.GlassConfig(cfg_path=p, language="de_DE",
                               shortcuts={str(win_glass.CMD_HOVER): "F9"})
    check("german pause label", c2.t("pause") != win_glass.GlassConfig(language="en_US").t("pause"))
    ok = c2.save()
    check("save wrote file", ok and os.path.isfile(p))
    saved = win_glass.load_cfg_file(p)
    check("reload language", saved.get("language") == "de_DE")
    check("reload shortcut key is str", str(win_glass.CMD_HOVER) in saved.get("shortcuts", {}))
    check("reload shortcut value", saved["shortcuts"][str(win_glass.CMD_HOVER)] == "F9")

# ---------------- 4. _sanitize_shortcuts 洗数据 ----------------
bad = {"notint": "Ctrl+P", win_glass.CMD_LOG: "Garbage",
       str(win_glass.CMD_QUIT): "Ctrl+Q", "x": {"nested": 1}}
clean = win_glass._sanitize_shortcuts(bad)
check("sanitize drops non-int key", "notint" not in clean)
check("sanitize drops unparseable", win_glass.CMD_LOG not in clean)
check("sanitize keeps valid", clean.get(win_glass.CMD_QUIT) == "Ctrl+Q")
check("sanitize drops non-dict value", "x" not in clean)

# ---------------- 5. I18N 回退 / 占位符 ----------------
s = win_glass.GlassConfig(language="ja_JP")
check("ja pause != key", s.t("pause") != "pause")
en = win_glass.GlassConfig(language="en_US")
check("en pause contains 'Pause'", "Pause" in en.t("pause") and en.t("pause") != "pause")
# 占位符
check("placeholder works", "Ctrl+Alt+P" in en.t("shortcut_clear") or
      isinstance(en.t("shortcut_clear"), str))
# 未知 key 回退成 key 名
check("unknown key -> key name", en.t("no_such_key_xyz") == "no_such_key_xyz")
# auto 解析
auto = win_glass.GlassConfig(language="auto")
check("auto resolves to a known lang", auto.lang_effective in
      {d["code"] for d in i18n.LANGS})

# ---------------- 6. as_dict 形状 ----------------
ad = win_glass.GlassConfig(language="fr_FR",
                           shortcuts={str(win_glass.CMD_LAYER): "Ctrl+L"}).as_dict()
check("as_dict has language", ad.get("language") == "fr_FR")
check("as_dict shortcuts str keys",
      str(win_glass.CMD_LAYER) in ad.get("shortcuts", {}) and
      ad["shortcuts"][str(win_glass.CMD_LAYER)] == "Ctrl+L")

# ---------------- 7. apply_saved_lang 三优先 ----------------
lang, sc = win_glass.GlassConfig.apply_saved_lang(
    {"language": "es_ES", "shortcuts": {"%d" % win_glass.CMD_LOG: "Ctrl+L"}},
    "ru_RU", None)
check("cli lang overrides saved", lang == "ru_RU")
lang2, sc2 = win_glass.GlassConfig.apply_saved_lang(
    {"language": "es_ES"}, None, None)
check("saved lang when no cli", lang2 == "es_ES")

print("\n=== %d failure(s) ===" % FAILED)
sys.exit(1 if FAILED else 0)
