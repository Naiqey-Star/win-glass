# -*- coding: utf-8 -*-
"""
win_glass_i18n.py —— 多语言文案 + 快捷键的“文本/解析”层。

放在独立模块里、而不是塞进 win_glass.py，有三个理由：
  1. 文案表很大（12 种语言 × 27 条），混在主程序里会淹没真正的逻辑；
  2. 这一层是**纯数据 + 纯函数**（不碰 ctypes、不碰窗口），可以脱离 GUI 单测；
  3. 加语言只需要往 STRINGS 里加一个键，不用动主程序一行。

⚠️ 设计约定
  - 键名一律是「中性英文标识符」，值是各语言的显示文本；
  - 取文本走 I18N.t(key)，**三级回退**：当前语言 → en_US → key 本身。
    这样某条文案漏翻译时不会显示空白，而是退化成英文，比崩掉/空字符串友好。
  - 带占位符的文案统一用 str.format 的 {name} 写法（不用 %），
    因为各语言语序不同（比如“与 A 冲突”在日语里是「A と競合しています」），
    只有具名占位符才能让译者自由调整语序。
"""

# --------------------------------------------------------------------------
# 语言清单
# --------------------------------------------------------------------------
# code       : 配置里存的键（写进 config.json 的 language 字段）
# native     : 菜单里显示的「本语言自称」，用户认得自己的语言比认英文快
# english    : 英文名，用于回退显示与调试
LANGS = [
    {"code": "auto",  "native": "跟随系统",              "english": "Follow system"},
    {"code": "zh_CN", "native": "简体中文",              "english": "Simplified Chinese"},
    {"code": "zh_TW", "native": "繁體中文",              "english": "Traditional Chinese"},
    {"code": "en_US", "native": "English",               "english": "English"},
    {"code": "ja_JP", "native": "日本語",                "english": "Japanese"},
    {"code": "ko_KR", "native": "한국어",                "english": "Korean"},
    {"code": "de_DE", "native": "Deutsch",               "english": "German"},
    {"code": "fr_FR", "native": "Français",              "english": "French"},
    {"code": "ru_RU", "native": "Русский",               "english": "Russian"},
    {"code": "ar_SA", "native": "العربية",               "english": "Arabic"},
    {"code": "pt_BR", "native": "Português (Brasil)",    "english": "Portuguese (Brazil)"},
    {"code": "es_ES", "native": "Español",               "english": "Spanish"},
    {"code": "it_IT", "native": "Italiano",              "english": "Italian"},
]

# 系统 UI 语言（GetUserDefaultUILanguage 返回的 LANGID 主语言部分）→ 我们的 code。
# 只列能确定映射的常见情况；查不到就回退 en_US。
_SYS_LANG_MAP = {
    0x04: "zh_CN",     # LANG_CHINESE (简体)
    0x11: "ja_JP",     # LANG_JAPANESE
    0x12: "ko_KR",     # LANG_KOREAN
    0x07: "de_DE",     # LANG_GERMAN
    0x0C: "fr_FR",     # LANG_FRENCH
    0x19: "ru_RU",     # LANG_RUSSIAN
    0x01: "ar_SA",     # LANG_ARABIC
    0x16: "pt_BR",     # LANG_PORTUGUESE
    0x0A: "es_ES",     # LANG_SPANISH
    0x10: "it_IT",     # LANG_ITALIAN
    0x09: "en_US",     # LANG_ENGLISH
}

DEFAULT_LANG = "auto"
FALLBACK_LANG = "en_US"

# --------------------------------------------------------------------------
# 文案表
# --------------------------------------------------------------------------
# 每条文案都用 str.format 具名占位符；没有占位符的就直接是文本。
STRINGS = {
    # ---------------- 简体中文 ----------------
    "zh_CN": {
        "tip":              "win_glass — 窗口聚焦透明",
        "pause":            "暂停（所有窗口恢复 100%）",
        "resume":           "已暂停（点击继续）",
        "restore":          "立即把所有窗口恢复 100%",
        "hover":            "悬停半透明（未聚焦窗口 → {pct}%）",
        "fullscreen_on":    "全屏窗口固定 100%（不受最高值设置影响）",
        "fullscreen_off":   "全屏窗口固定 100%（当前：完全不接管全屏）",
        "layer_on":         "层叠衰减（普通非聚焦逐层：{vals}…）",
        "layer_off":        "层叠衰减（当前：关，所有非聚焦统一 {pct}%）",
        "inactive":         "非聚焦最低透明度",
        "active":           "聚焦最高透明度",
        "hover_ratio":      "悬停插值系数",
        "decay":            "层衰减系数",
        "fade":             "渐隐时间…",
        "log":              "打开日志",
        "quit":             "退出（还原全部窗口）",
        "language":         "语言…",
        "shortcut_unset":   "右键设置快捷键",
        "shortcut_rec":     "请按下快捷键…",
        "shortcut_clear":   "按 Delete 清除当前绑定",
        "shortcut_conflict": "与「{name}」冲突",
        "shortcut_invalid": "无效的按键组合",
        "shortcut_failed":  "注册失败（可能被系统占用）",
        "fade_title":       "渐隐时间",
        "fade_prompt":      "渐隐时长（毫秒）：",
        "fade_unit":        "ms",
        "ok":               "确定",
        "cancel":           "取消",
    },
    # ---------------- 繁體中文 ----------------
    "zh_TW": {
        "tip":              "win_glass — 視窗聚焦透明",
        "pause":            "暫停（所有視窗恢復 100%）",
        "resume":           "已暫停（點擊繼續）",
        "restore":          "立即把所有視窗恢復 100%",
        "hover":            "懸停半透明（未聚焦視窗 → {pct}%）",
        "fullscreen_on":    "全螢幕視窗固定 100%（不受最高值設定影響）",
        "fullscreen_off":   "全螢幕視窗固定 100%（目前：完全不接管全螢幕）",
        "layer_on":         "層疊衰減（普通未聚焦逐層：{vals}…）",
        "layer_off":        "層疊衰減（目前：關閉，所有未聚焦統一 {pct}%）",
        "inactive":         "未聚焦最低透明度",
        "active":           "聚焦最高透明度",
        "hover_ratio":      "懸停插值係數",
        "decay":            "層衰減係數",
        "fade":             "漸隱時間…",
        "log":              "開啟記錄檔",
        "quit":             "結束（還原所有視窗）",
        "language":         "語言…",
        "shortcut_unset":   "右鍵設定快捷鍵",
        "shortcut_rec":     "請按下快捷鍵…",
        "shortcut_clear":   "按 Delete 清除目前綁定",
        "shortcut_conflict": "與「{name}」衝突",
        "shortcut_invalid": "無效的按鍵組合",
        "shortcut_failed":  "註冊失敗（可能被系統佔用）",
        "fade_title":       "漸隱時間",
        "fade_prompt":      "漸隱時長（毫秒）：",
        "fade_unit":        "ms",
        "ok":               "確定",
        "cancel":           "取消",
    },
    # ---------------- English ----------------
    "en_US": {
        "tip":              "win_glass — window focus transparency",
        "pause":            "Pause (restore all windows to 100%)",
        "resume":           "Paused (click to resume)",
        "restore":          "Restore all windows to 100% now",
        "hover":            "Hover translucency (unfocused → {pct}%)",
        "fullscreen_on":    "Keep fullscreen windows at 100% (ignores max setting)",
        "fullscreen_off":   "Keep fullscreen windows at 100% (currently: not managed)",
        "layer_on":         "Layer decay (unfocused stack: {vals}…)",
        "layer_off":        "Layer decay (off — all unfocused at {pct}%)",
        "inactive":         "Minimum opacity (unfocused)",
        "active":           "Maximum opacity (focused)",
        "hover_ratio":      "Hover interpolation",
        "decay":            "Layer decay factor",
        "fade":             "Fade duration…",
        "log":              "Open log",
        "quit":             "Quit (restore all windows)",
        "language":         "Language…",
        "shortcut_unset":   "Right-click to set a shortcut",
        "shortcut_rec":     "Press a shortcut key…",
        "shortcut_clear":   "Press Delete to clear",
        "shortcut_conflict": "Conflicts with “{name}”",
        "shortcut_invalid": "Invalid key combination",
        "shortcut_failed":  "Registration failed (may be taken by the system)",
        "fade_title":       "Fade duration",
        "fade_prompt":      "Fade duration (milliseconds):",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "Cancel",
    },
    # ---------------- 日本語 ----------------
    "ja_JP": {
        "tip":              "win_glass — ウィンドウフォーカス透明化",
        "pause":            "一時停止（すべてのウィンドウを 100% に戻す）",
        "resume":           "一時停止中（クリックで再開）",
        "restore":          "すべてのウィンドウをすぐに 100% に戻す",
        "hover":            "ホバー半透明（非フォーカス → {pct}%）",
        "fullscreen_on":    "全画面ウィンドウを 100% に固定（最大値の設定に影響しない）",
        "fullscreen_off":   "全画面ウィンドウを 100% に固定（現在：全画面を管理しない）",
        "layer_on":         "重なり減衰（非フォーカスの重なり順：{vals}…）",
        "layer_off":        "重なり減衰（オフ — 非フォーカスはすべて {pct}%）",
        "inactive":         "非フォーカス最小不透明度",
        "active":           "フォーカス最大不透明度",
        "hover_ratio":      "ホバー補間係数",
        "decay":            "重なり減衰係数",
        "fade":             "フェード時間…",
        "log":              "ログを開く",
        "quit":             "終了（すべてのウィンドウを復元）",
        "language":         "言語…",
        "shortcut_unset":   "右クリックでショートカットを設定",
        "shortcut_rec":     "ショートカットキーを押してください…",
        "shortcut_clear":   "Delete キーでクリア",
        "shortcut_conflict": "「{name}」と競合しています",
        "shortcut_invalid": "無効なキーの組み合わせ",
        "shortcut_failed":  "登録に失敗しました（システムで使用中の可能性）",
        "fade_title":       "フェード時間",
        "fade_prompt":      "フェード時間（ミリ秒）：",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "キャンセル",
    },
    # ---------------- 한국어 ----------------
    "ko_KR": {
        "tip":              "win_glass — 창 포커스 투명도",
        "pause":            "일시 정지 (모든 창을 100%로 복원)",
        "resume":           "일시 정지됨 (클릭하여 계속)",
        "restore":          "모든 창을 즉시 100%로 복원",
        "hover":            "호버 반투명 (비포커스 → {pct}%)",
        "fullscreen_on":    "전체 화면 창을 100%로 고정 (최대값 설정 무시)",
        "fullscreen_off":   "전체 화면 창을 100%로 고정 (현재: 전체 화면 관리 안 함)",
        "layer_on":         "겹침 감쇠 (비포커스 순서: {vals}…)",
        "layer_off":        "겹침 감쇠 (꺼짐 — 모든 비포커스 {pct}%)",
        "inactive":         "최소 불투명도 (비포커스)",
        "active":           "최대 불투명도 (포커스)",
        "hover_ratio":      "호버 보간 계수",
        "decay":            "겹침 감쇠 계수",
        "fade":             "전환 시간…",
        "log":              "로그 열기",
        "quit":             "종료 (모든 창 복원)",
        "language":         "언어…",
        "shortcut_unset":   "오른쪽 클릭으로 바로 가기 키 설정",
        "shortcut_rec":     "바로 가기 키를 누르세요…",
        "shortcut_clear":   "Delete 키로 해제",
        "shortcut_conflict": "「{name}」와(과) 충돌",
        "shortcut_invalid": "잘못된 키 조합",
        "shortcut_failed":  "등록 실패 (시스템에서 사용 중일 수 있음)",
        "fade_title":       "전환 시간",
        "fade_prompt":      "전환 시간(밀리초):",
        "fade_unit":        "ms",
        "ok":               "확인",
        "cancel":           "취소",
    },
    # ---------------- Deutsch ----------------
    "de_DE": {
        "tip":              "win_glass — Fensterfokus-Transparenz",
        "pause":            "Pause (alle Fenster auf 100 % zurücksetzen)",
        "resume":           "Pausiert (klicken zum Fortsetzen)",
        "restore":          "Alle Fenster sofort auf 100 % zurücksetzen",
        "hover":            "Hover-Transparenz (ohne Fokus → {pct} %)",
        "fullscreen_on":    "Vollbildfenster auf 100 % fixieren (unabhängig vom Maximalwert)",
        "fullscreen_off":   "Vollbildfenster auf 100 % fixieren (aktuell: nicht verwaltet)",
        "layer_on":         "Stapelabstufung (nicht fokussierte Ebenen: {vals}…)",
        "layer_off":        "Stapelabstufung (aus — alle ohne Fokus {pct} %)",
        "inactive":         "Minimale Deckkraft (ohne Fokus)",
        "active":           "Maximale Deckkraft (Fokus)",
        "hover_ratio":      "Hover-Interpolation",
        "decay":            "Stapelabstufungsfaktor",
        "fade":             "Überblenddauer…",
        "log":              "Protokoll öffnen",
        "quit":             "Beenden (alle Fenster zurücksetzen)",
        "language":         "Sprache…",
        "shortcut_unset":   "Rechtsklick zum Festlegen einer Tastenkombination",
        "shortcut_rec":     "Tastenkombination drücken…",
        "shortcut_clear":   "Mit Entf-Taste löschen",
        "shortcut_conflict": "Konflikt mit „{name}“",
        "shortcut_invalid": "Ungültige Tastenkombination",
        "shortcut_failed":  "Registrierung fehlgeschlagen (vom System belegt?)",
        "fade_title":       "Überblenddauer",
        "fade_prompt":      "Überblenddauer (Millisekunden):",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "Abbrechen",
    },
    # ---------------- Français ----------------
    "fr_FR": {
        "tip":              "win_glass — transparence selon le focus",
        "pause":            "Pause (restaurer toutes les fenêtres à 100 %)",
        "resume":           "En pause (cliquer pour reprendre)",
        "restore":          "Restaurer toutes les fenêtres à 100 % maintenant",
        "hover":            "Transparence au survol (non focalisé → {pct} %)",
        "fullscreen_on":    "Garder le plein écran à 100 % (ignore le réglage maximal)",
        "fullscreen_off":   "Garder le plein écran à 100 % (actuellement : non géré)",
        "layer_on":         "Atténuation par couche (empilement : {vals}…)",
        "layer_off":        "Atténuation par couche (désactivée — tout à {pct} %)",
        "inactive":         "Opacité minimale (non focalisé)",
        "active":           "Opacité maximale (focalisé)",
        "hover_ratio":      "Interpolation au survol",
        "decay":            "Facteur d'atténuation",
        "fade":             "Durée du fondu…",
        "log":              "Ouvrir le journal",
        "quit":             "Quitter (restaurer toutes les fenêtres)",
        "language":         "Langue…",
        "shortcut_unset":   "Clic droit pour définir un raccourci",
        "shortcut_rec":     "Appuyez sur une touche…",
        "shortcut_clear":   "Appuyer sur Suppr pour effacer",
        "shortcut_conflict": "Conflit avec « {name} »",
        "shortcut_invalid": "Combinaison de touches invalide",
        "shortcut_failed":  "Échec de l'enregistrement (peut-être pris par le système)",
        "fade_title":       "Durée du fondu",
        "fade_prompt":      "Durée du fondu (millisecondes) :",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "Annuler",
    },
    # ---------------- Русский ----------------
    "ru_RU": {
        "tip":              "win_glass — прозрачность по фокусу окна",
        "pause":            "Пауза (вернуть все окна к 100%)",
        "resume":           "Пауза (нажмите, чтобы продолжить)",
        "restore":          "Сейчас вернуть все окна к 100%",
        "hover":            "Прозрачность при наведении (без фокуса → {pct}%)",
        "fullscreen_on":    "Держать полноэкранные окна на 100% (не зависит от максимума)",
        "fullscreen_off":   "Держать полноэкранные окна на 100% (сейчас: не управляются)",
        "layer_on":         "Затухание по слоям (стопка без фокуса: {vals}…)",
        "layer_off":        "Затухание по слоям (выключено — все без фокуса {pct}%)",
        "inactive":         "Минимальная непрозрачность (без фокуса)",
        "active":           "Максимальная непрозрачность (в фокусе)",
        "hover_ratio":      "Коэффициент наведения",
        "decay":            "Коэффициент затухания",
        "fade":             "Длительность перехода…",
        "log":              "Открыть журнал",
        "quit":             "Выход (вернуть все окна)",
        "language":         "Язык…",
        "shortcut_unset":   "Щёлкните правой кнопкой, чтобы задать сочетание",
        "shortcut_rec":     "Нажмите сочетание клавиш…",
        "shortcut_clear":   "Нажмите Delete, чтобы сбросить",
        "shortcut_conflict": "Конфликт с «{name}»",
        "shortcut_invalid": "Недопустимое сочетание клавиш",
        "shortcut_failed":  "Не удалось зарегистрировать (возможно, занято системой)",
        "fade_title":       "Длительность перехода",
        "fade_prompt":      "Длительность перехода (миллисекунды):",
        "fade_unit":        "мс",
        "ok":               "OK",
        "cancel":           "Отмена",
    },
    # ---------------- العربية ----------------
    "ar_SA": {
        "tip":              "win_glass — شفافية حسب تركيز النافذة",
        "pause":            "إيقاف مؤقت (إعادة كل النوافذ إلى ‎100%‎)",
        "resume":           "متوقف مؤقتًا (انقر للمتابعة)",
        "restore":          "إعادة كل النوافذ إلى ‎100%‎ الآن",
        "hover":            "شفافية عند المرور (بدون تركيز → {pct}‎%‎)",
        "fullscreen_on":    "تثبيت النوافذ بكامل الشاشة على ‎100%‎ (لا يتأثر بالحد الأقصى)",
        "fullscreen_off":   "تثبيت النوافذ بكامل الشاشة على ‎100%‎ (الحالي: لا تُدار)",
        "layer_on":         "تدرّج الطبقات (ترتيب النوافذ بدون تركيز: {vals}…)",
        "layer_off":        "تدرّج الطبقات (معطّل — كل النوافذ بدون تركيز {pct}‎%‎)",
        "inactive":         "أدنى تعتيم (بدون تركيز)",
        "active":           "أقصى تعتيم (في التركيز)",
        "hover_ratio":      "معامل المرور",
        "decay":            "معامل تدرّج الطبقات",
        "fade":             "مدة التلاشي…",
        "log":              "فتح السجل",
        "quit":             "خروج (إعادة كل النوافذ)",
        "language":         "اللغة…",
        "shortcut_unset":   "انقر بزر الفأرة الأيمن لتعيين اختصار",
        "shortcut_rec":     "اضغط مفتاح الاختصار…",
        "shortcut_clear":   "اضغط Delete للحذف",
        "shortcut_conflict": "يتعارض مع «{name}»",
        "shortcut_invalid": "تركيبة مفاتيح غير صالحة",
        "shortcut_failed":  "فشل التسجيل (قد تكون مستخدمة من النظام)",
        "fade_title":       "مدة التلاشي",
        "fade_prompt":      "مدة التلاشي (بالملي ثانية):",
        "fade_unit":        "ms",
        "ok":               "موافق",
        "cancel":           "إلغاء",
    },
    # ---------------- Português (Brasil) ----------------
    "pt_BR": {
        "tip":              "win_glass — transparência por foco da janela",
        "pause":            "Pausar (restaurar todas as janelas para 100%)",
        "resume":           "Pausado (clique para continuar)",
        "restore":          "Restaurar todas as janelas para 100% agora",
        "hover":            "Transparência ao passar o mouse (sem foco → {pct}%)",
        "fullscreen_on":    "Manter janelas em tela cheia a 100% (ignora o valor máximo)",
        "fullscreen_off":   "Manter janelas em tela cheia a 100% (atualmente: não gerenciadas)",
        "layer_on":         "Atenuação por camada (pilha sem foco: {vals}…)",
        "layer_off":        "Atenuação por camada (desligada — todas sem foco a {pct}%)",
        "inactive":         "Opacidade mínima (sem foco)",
        "active":           "Opacidade máxima (com foco)",
        "hover_ratio":      "Interpolação ao passar o mouse",
        "decay":            "Fator de atenuação por camada",
        "fade":             "Duração da transição…",
        "log":              "Abrir registro",
        "quit":             "Sair (restaurar todas as janelas)",
        "language":         "Idioma…",
        "shortcut_unset":   "Clique com o botão direito para definir um atalho",
        "shortcut_rec":     "Pressione uma tecla de atalho…",
        "shortcut_clear":   "Pressione Delete para limpar",
        "shortcut_conflict": "Conflito com “{name}”",
        "shortcut_invalid": "Combinação de teclas inválida",
        "shortcut_failed":  "Falha ao registrar (pode estar em uso pelo sistema)",
        "fade_title":       "Duração da transição",
        "fade_prompt":      "Duração da transição (milissegundos):",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "Cancelar",
    },
    # ---------------- Español ----------------
    "es_ES": {
        "tip":              "win_glass — transparencia según el foco",
        "pause":            "Pausar (restaurar todas las ventanas al 100%)",
        "resume":           "En pausa (haz clic para continuar)",
        "restore":          "Restaurar todas las ventanas al 100% ahora",
        "hover":            "Translucidez al pasar el cursor (sin foco → {pct}%)",
        "fullscreen_on":    "Mantener ventanas a pantalla completa al 100% (ignora el máximo)",
        "fullscreen_off":   "Mantener ventanas a pantalla completa al 100% (ahora: no gestionadas)",
        "layer_on":         "Atenuación por capas (pila sin foco: {vals}…)",
        "layer_off":        "Atenuación por capas (desactivada — todas sin foco al {pct}%)",
        "inactive":         "Opacidad mínima (sin foco)",
        "active":           "Opacidad máxima (con foco)",
        "hover_ratio":      "Interpolación al pasar el cursor",
        "decay":            "Factor de atenuación por capas",
        "fade":             "Duración del fundido…",
        "log":              "Abrir registro",
        "quit":             "Salir (restaurar todas las ventanas)",
        "language":         "Idioma…",
        "shortcut_unset":   "Haz clic derecho para definir un atajo",
        "shortcut_rec":     "Pulsa una tecla de atajo…",
        "shortcut_clear":   "Pulsa Supr para borrar",
        "shortcut_conflict": "Conflicto con «{name}»",
        "shortcut_invalid": "Combinación de teclas no válida",
        "shortcut_failed":  "Error al registrar (puede estar en uso por el sistema)",
        "fade_title":       "Duración del fundido",
        "fade_prompt":      "Duración del fundido (milisegundos):",
        "fade_unit":        "ms",
        "ok":               "Aceptar",
        "cancel":           "Cancelar",
    },
    # ---------------- Italiano ----------------
    "it_IT": {
        "tip":              "win_glass — trasparenza in base al focus",
        "pause":            "Pausa (ripristina tutte le finestre al 100%)",
        "resume":           "In pausa (fai clic per riprendere)",
        "restore":          "Ripristina subito tutte le finestre al 100%",
        "hover":            "Trasparenza al passaggio del mouse (senza focus → {pct}%)",
        "fullscreen_on":    "Mantieni le finestre a schermo intero al 100% (ignora il massimo)",
        "fullscreen_off":   "Mantieni le finestre a schermo intero al 100% (ora: non gestite)",
        "layer_on":         "Attenuazione a strati (pila senza focus: {vals}…)",
        "layer_off":        "Attenuazione a strati (disattivata — tutte senza focus al {pct}%)",
        "inactive":         "Opacità minima (senza focus)",
        "active":           "Opacità massima (con focus)",
        "hover_ratio":      "Interpolazione al passaggio del mouse",
        "decay":            "Fattore di attenuazione",
        "fade":             "Durata della dissolvenza…",
        "log":              "Apri il registro",
        "quit":             "Esci (ripristina tutte le finestre)",
        "language":         "Lingua…",
        "shortcut_unset":   "Fai clic destro per impostare una scorciatoia",
        "shortcut_rec":     "Premi un tasto di scelta rapida…",
        "shortcut_clear":   "Premi Canc per cancellare",
        "shortcut_conflict": "Conflitto con «{name}»",
        "shortcut_invalid": "Combinazione di tasti non valida",
        "shortcut_failed":  "Registrazione non riuscita (forse occupata dal sistema)",
        "fade_title":       "Durata della dissolvenza",
        "fade_prompt":      "Durata della dissolvenza (millisecondi):",
        "fade_unit":        "ms",
        "ok":               "OK",
        "cancel":           "Annulla",
    },
}


# --------------------------------------------------------------------------
# 取值
# --------------------------------------------------------------------------
def lang_codes():
    """返回所有可选语言的 code 列表（含 auto）。"""
    return [d["code"] for d in LANGS]


def lang_name(code):
    """菜单里显示的名字（本语言自称）。"""
    for d in LANGS:
        if d["code"] == code:
            return d["native"]
    return code


def is_known_lang(code):
    return code in STRINGS or code == DEFAULT_LANG


class I18N:
    """按语言取文案。

    三级回退：当前语言 → en_US → 键名本身。
    最后一级保证「漏翻译」不会让界面出现空白或抛异常。
    """

    def __init__(self, lang: str = DEFAULT_LANG, sys_lang: str = FALLBACK_LANG):
        self.sys_lang = sys_lang if sys_lang in STRINGS else FALLBACK_LANG
        self.set(lang)

    def set(self, lang: str):
        self.lang = lang if lang in STRINGS else (
            self.sys_lang if lang == DEFAULT_LANG else FALLBACK_LANG)
        # auto：解析成实际系统语言，但 config 里仍然存 "auto"
        self.requested = lang if lang in STRINGS or lang == DEFAULT_LANG \
            else DEFAULT_LANG
        return self.lang

    @property
    def effective(self) -> str:
        """当前实际生效的语言 code（auto 会被解析掉）。"""
        return self.lang

    def t(self, key: str, **kw) -> str:
        tbl = STRINGS.get(self.lang) or {}
        s = tbl.get(key)
        if s is None:
            s = (STRINGS.get(FALLBACK_LANG) or {}).get(key, key)
        try:
            return s.format(**kw) if kw else s
        except Exception:
            # 占位符对不上时宁可显示未格式化的原文，也不要炸掉整个菜单绘制
            return s


def detect_sys_lang(langid: int = 0) -> str:
    """把系统 UI 语言的 LANGID 映射成我们的语言 code。

    langid=0 表示调用方没拿到（比如非 Windows），直接回退英文。
    """
    if not langid:
        return FALLBACK_LANG
    primary = langid & 0x3FF
    # 中文要区分简繁：SUBLANG_CHINESE_TRADITIONAL(0x01) / SIMPLIFIED(0x02)
    if primary == 0x04:
        sub = (langid >> 10) & 0x3F
        return "zh_TW" if sub in (0x01, 0x03, 0x04) else "zh_CN"
    return _SYS_LANG_MAP.get(primary, FALLBACK_LANG)


# --------------------------------------------------------------------------
# 快捷键：显示名 / 解析
# --------------------------------------------------------------------------
# 修饰键顺序固定成 Ctrl / Alt / Shift / Win，和 Windows 习惯一致
MOD_CTRL, MOD_ALT, MOD_SHIFT, MOD_WIN = 2, 1, 4, 8

_MOD_ORDER = (("Ctrl", MOD_CTRL), ("Alt", MOD_ALT),
              ("Shift", MOD_SHIFT), ("Win", MOD_WIN))

# 需要显示成文字（而不是单个字符）的常见虚拟键
VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc",
    0x20: "Space", 0x21: "PgUp", 0x22: "PgDn", 0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrtSc", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "Win", 0x5C: "Win",
    0x60: "Num0", 0x61: "Num1", 0x62: "Num2", 0x63: "Num3", 0x64: "Num4",
    0x65: "Num5", 0x66: "Num6", 0x67: "Num7", 0x68: "Num8", 0x69: "Num9",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0x0C: "Num5",
    0x90: "NumLock", 0x91: "ScrollLock", 0x13: "Pause",
    0xA0: "Shift", 0xA1: "Shift", 0xA2: "Ctrl", 0xA3: "Ctrl",
    0xA4: "Alt", 0xA5: "Alt",
}

# 这些键**不能**作为主键参与组合：要么是修饰键本身，要么是用来取消录制的键
_MODIFIER_VKS = {
    0x10, 0x11, 0x12,                     # Shift / Ctrl / Alt
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,   # 左右分开的 Shift/Ctrl/Alt
    0x5B, 0x5C,                           # 左右 Win
}
_RESERVED_VKS = {0x1B}                    # Esc：留给「取消录制」

# 功能键 F1~F24
for _i in range(1, 25):
    VK_NAMES[0x6F + _i] = "F%d" % _i


def vk_name(vk: int) -> str:
    """虚拟键 → 显示名（A / 5 / F5 / Ctrl / Space …）。"""
    vk = int(vk)
    if vk in VK_NAMES:
        return VK_NAMES[vk]
    if 0x30 <= vk <= 0x39:                # 主键盘数字
        return chr(vk)
    if 0x41 <= vk <= 0x5A:                # A~Z
        return chr(vk)
    if 0xBA <= vk <= 0xC0 or 0xDB <= vk <= 0xDF:
        # 标点符号键：不同键盘布局差异很大，用 VK 码兜底比猜字符稳
        return "VK%02X" % vk
    return "VK%02X" % vk


def format_combo(mods: int, vk: int) -> str:
    """(修饰键位掩码, 主键) → "Ctrl+Alt+P" 这种显示文本。"""
    parts = [name for name, bit in _MOD_ORDER if int(mods) & bit]
    parts.append(vk_name(vk))
    return "+".join(parts)


def parse_combo(text: str):
    """"Ctrl+Alt+P" → (mods, vk)；解析不出来返回 None。

    这是 format_combo 的逆运算，落盘读回来要用。主键用 vk_name 反查，
    所以这里建了一张「显示名 → VK」的反表。
    """
    if not text:
        return None
    parts = [p.strip() for p in str(text).split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    vk = None
    name_to_vk = {}
    for k, v in VK_NAMES.items():
        name_to_vk.setdefault(v, k)
    for p in parts:
        low = p.lower()
        if low == "ctrl":
            mods |= MOD_CTRL
        elif low == "alt":
            mods |= MOD_ALT
        elif low == "shift":
            mods |= MOD_SHIFT
        elif low == "win":
            mods |= MOD_WIN
        else:
            if len(p) == 1:
                vk = ord(p.upper())
            elif p in name_to_vk:
                vk = name_to_vk[p]
            else:
                return None
    if vk is None:
        return None
    return mods, vk


def is_bindable_vk(vk: int) -> bool:
    """这个虚拟键能不能当快捷键的主键？"""
    vk = int(vk)
    if vk in _MODIFIER_VKS or vk in _RESERVED_VKS:
        return False
    if vk in (0x01, 0x02, 0x04, 0x05, 0x06):   # 鼠标键
        return False
    return 0 < vk < 0xFF


def normalize_combo(mods: int, vk: int):
    """归一化：夹掉不合法输入，返回 (mods, vk) 或 None。"""
    try:
        mods, vk = int(mods), int(vk)
    except Exception:
        return None
    if not is_bindable_vk(vk):
        return None
    m = 0
    for _name, bit in _MOD_ORDER:
        if mods & bit:
            m |= bit
    return m, vk
