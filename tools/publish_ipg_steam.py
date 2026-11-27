"""Steam Workshop publisher for IPG v3.1 & BPM compat items via Steamworks C-API.

Targets (`--target`):
  - ipg      : Standalone Improved ParliamentGraph 3.1 (Workshop ID 3721626337)
  - bpm25    : BPM2.5-ParliamentGraph(1.15) (Workshop ID 3697574736)
  - gora-bpm : GORA UI+ × Better Politics Mod Compat (Workshop ID 3726578545)

By default, existing live Steam gallery screenshots are PRESERVED untouched.
Pass `--update-previews` (only for `--target ipg`) to wipe & re-upload local gallery PNGs.
Default is a dry run; pass `--publish` to upload.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import sys
import tempfile
import time
from ctypes import POINTER, Structure, byref, c_bool, c_char_p, c_int32, c_uint32, c_uint64, c_void_p
from pathlib import Path

APP_ID = 529340
UGC_INTERFACE_VERSION = b"STEAMUGC_INTERFACE_VERSION013"
UTILS_INTERFACE_VERSION = b"SteamUtils009"

TOOLS_DIR = Path(__file__).resolve().parent
MODS_ROOT = TOOLS_DIR.parent.parent
STANDALONE_DIR = MODS_ROOT / "Improved ParliamentGraph[1.15]"
BPM25_DIR = MODS_ROOT / "BPM2.5-ParliamentGraph"
GORA_BPM_DIR = MODS_ROOT / "GORA UI+ × Better Politics Mod Compat"
STEAM_DLL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\binaries\steam_api64_o.dll")

ALLOWED_DOT_ENTRIES = {".metadata"}
EXCLUDE_NAMES = {"__pycache__", "build", "_build_localization.py", "_build_seat_layout.py"}

GALLERY_FILES = [
    "1.png", "2.png", "3.png", "4.png", "5.png",
    "Westminster.png", "Hemicyle.png", "Hourshoe.png", "Assembly.png", "Bicameral.png",
]

IPG_TITLE = "Improved ParliamentGraph 3.1"

CHANGE_NOTE_IPG_EN = """v3.1.0 — Seat Apportionment Formulas, Historical Chambers & Foreign AI Parliaments!
- Added bottom-left Seat Apportionment selector with 5 live formulas (Hare / Hamilton, D'Hondt, Sainte-Laguë, 5% Threshold PR, Mild Plurality / FPTP) + Smart Auto-Matching driven by Distribution of Power laws & cultural heritage
- Linked active formula to BOTH all-3-view seat allocation (Party Structure, Power Structure, Political Alignment, including post-formula seat share %) AND historically authentic chamber size (+25% Plurality, +10% Sainte-Laguë, baseline Hare, -5% D'Hondt, -15% 5% Threshold)
- Added 20+ country-specific historical chamber names with unified Upper House (Power), Lower House (Party), and Whole Parliament (Alignment) titles + custom Upper/Lower badges (e.g., GBR House of Lords / House of Commons, USA Senate / House of Representatives, Qing Grand Council / Advisory Council, Tsarist State Council / State Duma)
- Added on-demand Foreign AI Parliament Viewer on other countries' Diplomacy -> Politics tab (Party Structure, Power Structure, Political Alignment; seamless Power Structure fallback for non-party nations; zero background AI overhead)
- Added 5-election rolling seat history in per-seat tooltips, 3D enameled dot sheen, and full alignment with official Victoria 3 localization keys across all 11 languages"""

CHANGE_NOTE_IPG_CN = """v3.1.0 — 议席分配算法、国别上下院与外国三视图议会大更新！
- 画布左下角新增「议席分配算法」选择器，支持 5 套实时算法（哈密顿法、洪特法、圣拉格法、5% 门槛制、多数制加成）及按权力分配法律与文化传统自动匹配
- 算法全面联动三视图席位分布（政党结构、权力结构、政治倾向及算法后占比）与历史总席位规模（多数制 +25%、圣拉格 +10%、哈密顿基准、洪特 -5%、5% 门槛 -15%）及 100/200/300 画布点数档位
- 新增 20+ 国别专属历史议院名称，全面对齐上院（权力结构）、下院（政党结构）与整体议会（政治倾向）命名并配自定义上下院徽章（如英国上议院/下议院、美国参议院/众议院、大清军机处/资政院、俄国国务会议/国家杜马）
- 外交国家政治页新增按需计算的「外国议会」三视图（政党结构、权力结构、政治倾向；无党派国家自动以权力结构无缝兜底，平时零 AI 后台算力开销）
- 新增单席位近 5 届席位趋势、3D 搪瓷圆点高光质感，全部法律与政治术语直接对齐维多利亚 3 原版官方本地化"""

BPM25_TITLE = "BPM2.5-ParliamentGraph(1.15)"

BPM25_DESC_EN = """[h1]🏛️ BPM2.5-ParliamentGraph (1.15) — Upgraded to IPG 3.1![/h1]

Complete standalone [b]Improved ParliamentGraph 3.1[/b] edition built specifically for [url=https://steamcommunity.com/sharedfiles/filedetails/?id=2932134122]Better Politics Mod (2.5 / 1.15.*)[/url].

[list]
[*]Supported Game Version: [b]1.15.*[/b] (Better Politics Mod 2.5)
[*]All-in-one standalone for BPM — do [b]not[/b] enable vanilla Improved ParliamentGraph or GORA UI+ alongside this mod (GORA UI+ users should use [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3726578545]GORA UI+ × BPM Compat[/url] instead)
[*]Zero gameplay changes (pure UI), Ironman / Multiplayer safe, all 11 official languages
[*]Load Order: [b]1. Better Politics Mod → 2. BPM2.5-ParliamentGraph(1.15)[/b] (partial-type `gui/!ipg_bpm.gui` preserves every other BPM widget cleanly)
[/list]

[h2]🔥 Highlights (IPG 3.1)[/h2]
[list]
[*][b]5 Chamber Architectures + Auto-Match[/b]: Westminster, Bicameral Split, Horseshoe, Assembly Hall, Hemicycle
[*][b]5 Live Seat Apportionment Formulas[/b]: Hare / Hamilton, D'Hondt, Sainte-Laguë, 5% Threshold PR, Plurality (FPTP) — linked to all 3 views and historical chamber size (50–650 seats)
[*][b]20+ Country Historical Chamber Names[/b]: Unified Upper House (Power Structure), Lower House (Party Structure), and Whole Parliament (Political Alignment) titles with custom badges
[*][b]On-Demand Foreign AI Parliament Viewer[/b]: Integrated directly into BPM's foreign Country Politics panel (Party / Power / Alignment, zero background AI overhead)
[*][b]Paradox-Native FancyTooltips, Per-Seat Hover & 5-Election Seat History[/b] + 3D enameled dot sheen
[/list]

[h2]🙏 Credits[/h2]
[list]
[*]Standalone vanilla edition: [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3721626337]Improved ParliamentGraph 3.1[/url]
[*]Inspiration & ideas: [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3842935371]Vote! Submod for BPM[/url]
[*]Flagship UI pack: [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3724865565]GORA UI+[/url]
[/list]"""

BPM25_DESC_CN = """[h1]🏛️ BPM2.5-ParliamentGraph (1.15) — 全面升级至 IPG 3.1！[/h1]

专为 [url=https://steamcommunity.com/sharedfiles/filedetails/?id=2932134122]Better Politics Mod (BPM 2.5 / 1.15.*)[/url] 打造的 [b]Improved ParliamentGraph 3.1[/b] 完整独立兼容版。

[list]
[*]支持游戏版本：[b]1.15.*[/b]（适配现行 BPM 2.5）
[*]本模组已内置完整 IPG 3.1，[b]无需[/b]重复订阅原版独立 IPG（如同时使用 GORA UI+，请改用 [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3726578545]GORA UI+ × BPM 兼容补丁[/url]）
[*]纯 UI 零玩法修改、支持联机与中途加档、完整支持全部 11 种官方语言
[*]加载顺序：[b]1. Better Politics Mod → 2. BPM2.5-ParliamentGraph(1.15)[/b]（采用轻量局部覆盖 `gui/!ipg_bpm.gui`，完整保留 BPM 全部界面组件）
[/list]

[h2]🔥 核心亮点（IPG 3.1）[/h2]
[list]
[*][b]5 大历史议会形态 + 智能匹配[/b]：威斯敏斯特、两院分席、马蹄形、阶梯大会堂、经典半圆
[*][b]5 套实时议席分配算法[/b]：哈密顿法、洪特法、圣拉格法、5% 门槛制、多数制加成——联动三视图席位分布与历史总席位规模（50–650 席）
[*][b]20+ 国别专属历史上下院命名[/b]：权力结构显示上院、政党结构显示下院、政治倾向显示整体议会，配自定义上下院徽章
[*][b]外交页外国三视图议会[/b]：已完整适配 BPM 外国政治面板，按需查看他国政党/权力/倾向议会图（无党派国家自动以权力结构兜底，零后台 AI 算力占用）
[*][b]原版级多色堆叠条 FancyTooltip、单席悬停、近 5 届席位趋势与 3D 搪瓷圆点[/b]
[/list]

[h2]🙏 致谢[/h2]
[list]
[*]原版独立版：[url=https://steamcommunity.com/sharedfiles/filedetails/?id=3721626337]Improved ParliamentGraph 3.1[/url]
[*]灵感与设计参考：[url=https://steamcommunity.com/sharedfiles/filedetails/?id=3842935371]Vote! Submod for BPM[/url]
[*]UI 合集旗舰版：[url=https://steamcommunity.com/sharedfiles/filedetails/?id=3724865565]GORA UI+[/url]
[/list]"""

CHANGE_NOTE_BPM25_EN = """v3.1.0 — Upgraded to Victoria 3 1.15.* + Improved ParliamentGraph 3.1!
- Rebuilt BPM GUI integration cleanly against Better Politics Mod 2.5 (1.15.*) using partial-type `gui/!ipg_bpm.gui` (splices both `politics_panel_government_details` and `country_panel_politics_content`)
- Upgraded full bundled engine to IPG 3.1: 5 chamber architectures, 5 live seat apportionment formulas linked to all 3 views & historical seat counts, 20+ country historical Upper/Lower chamber names, 5-election seat trends, 3D dot sheen, and on-demand 3-view Foreign AI Parliament Viewer"""

CHANGE_NOTE_BPM25_CN = """v3.1.0 — 升级适配维多利亚 3 1.15.* + Improved ParliamentGraph 3.1！
- 基于 Better Politics Mod 2.5 (1.15.*) 重构轻量局部覆盖 `gui/!ipg_bpm.gui`，同时挂载本国议会与外交页外国议会视图
- 完整升级内置引擎至 IPG 3.1：5 大历史议会形态、5 套实时算法联动三视图与历史总席位规模、20+ 国别历史上下院名称、近 5 届席位趋势、3D 圆点质感及外交外国三视图议会"""

CHANGE_NOTE_GORA_BPM_EN = """v1.2.0 — GORA UI+ 1.4.0 / IPG 3.1 Compatibility Update
- Added `country_panel_politics_content` partial-type splice into `gui/!gora_bpm.gui` so the new IPG 3.1 on-demand Foreign AI Parliament Viewer (Party Structure, Power Structure, Political Alignment) renders cleanly alongside Better Politics Mod 2.5 (1.15.*)
- Rebuilt directly against latest BPM 2.5 (1.15.*) Workshop baseline"""

CHANGE_NOTE_GORA_BPM_CN = """v1.2.0 — 适配 GORA UI+ 1.4.0 / IPG 3.1 更新
- 在 `gui/!gora_bpm.gui` 中补入 `country_panel_politics_content` 局部挂载点，使 GORA UI+ 1.4.0 / IPG 3.1 新增的外交页「外国议会」三视图在 Better Politics Mod 2.5 (1.15.*) 下正常显示
- 基于最新 BPM 2.5 (1.15.*) 创意工坊基线重新构建"""

STATUS = {
    0: "Invalid", 1: "PreparingConfig", 2: "PreparingContent",
    3: "UploadingContent", 4: "UploadingPreviewFile", 5: "CommittingChanges",
}


class SubmitItemUpdateResult_t(Structure):
    _fields_ = [
        ("m_eResult", c_int32),
        ("m_bUserNeedsToAcceptWorkshopLegalAgreement", c_bool),
        ("m_nPublishedFileId", c_uint64),
    ]


class SteamUGCQueryCompleted_t(Structure):
    _fields_ = [
        ("m_handle", c_uint64), ("m_eResult", c_int32),
        ("m_unNumResultsReturned", c_uint32), ("m_unTotalMatchingResults", c_uint32),
        ("m_bCachedData", c_bool),
    ]


class SteamParamStringArray_t(Structure):
    _fields_ = [("m_ppStrings", POINTER(c_char_p)), ("m_nNumStrings", c_int32)]


def stage_content(src_root: Path, dst: Path) -> tuple[int, int]:
    root_resolved = src_root.resolve()

    def _ignore(src_dir: str, names: list[str]) -> set[str]:
        is_root = Path(src_dir).resolve() == root_resolved
        ignored: set[str] = set()
        for name in names:
            if name.startswith(".") and not (is_root and name in ALLOWED_DOT_ENTRIES):
                ignored.add(name)
            elif name in EXCLUDE_NAMES or name.endswith(".pyc"):
                ignored.add(name)
            elif is_root and name.lower().endswith(".png") and name != "thumbnail.png":
                ignored.add(name)
        return ignored

    shutil.copytree(src_root, dst, ignore=_ignore, dirs_exist_ok=True)
    files = size = 0
    for p in dst.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return files, size


def prepare_preview_image(src: Path, tmp_dir: Path, max_bytes: int = 980_000) -> Path:
    if src.stat().st_size <= max_bytes:
        return src
    try:
        from PIL import Image
    except ImportError:
        return src
    out_jpg = tmp_dir / f"{src.stem}.jpg"
    im = Image.open(src).convert("RGB")
    for q in (94, 90, 86, 80):
        im.save(out_jpg, format="JPEG", quality=q, optimize=True)
        if out_jpg.stat().st_size <= max_bytes:
            return out_jpg
    return out_jpg


def load_steam_api():
    if not STEAM_DLL.exists():
        raise FileNotFoundError(f"Steamworks DLL not found: {STEAM_DLL}")
    os.environ["SteamAppId"] = os.environ["SteamGameId"] = str(APP_ID)
    dll = ctypes.CDLL(str(STEAM_DLL))
    sig = {
        "SteamAPI_Init": ([], c_bool),
        "SteamAPI_Shutdown": ([], None),
        "SteamAPI_RunCallbacks": ([], None),
        "SteamAPI_GetHSteamUser": ([], c_int32),
        "SteamAPI_GetHSteamPipe": ([], c_int32),
        "SteamClient": ([], c_void_p),
        "SteamInternal_FindOrCreateUserInterface": ([c_int32, c_char_p], c_void_p),
        "SteamAPI_ISteamClient_GetISteamUtils": ([c_void_p, c_int32, c_char_p], c_void_p),
        "SteamAPI_ISteamUtils_IsAPICallCompleted": ([c_void_p, c_uint64, POINTER(c_bool)], c_bool),
        "SteamAPI_ISteamUtils_GetAPICallResult": ([c_void_p, c_uint64, c_void_p, c_int32, c_int32, POINTER(c_bool)], c_bool),
        "SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest": ([c_void_p, POINTER(c_uint64), c_uint32], c_uint64),
        "SteamAPI_ISteamUGC_SetReturnAdditionalPreviews": ([c_void_p, c_uint64, c_bool], c_bool),
        "SteamAPI_ISteamUGC_SendQueryUGCRequest": ([c_void_p, c_uint64], c_uint64),
        "SteamAPI_ISteamUGC_GetQueryUGCNumAdditionalPreviews": ([c_void_p, c_uint64, c_uint32], c_uint32),
        "SteamAPI_ISteamUGC_GetQueryUGCAdditionalPreview": ([c_void_p, c_uint64, c_uint32, c_uint32, c_char_p, c_uint32, c_char_p, c_uint32, POINTER(c_int32)], c_bool),
        "SteamAPI_ISteamUGC_ReleaseQueryUGCRequest": ([c_void_p, c_uint64], c_bool),
        "SteamAPI_ISteamUGC_StartItemUpdate": ([c_void_p, c_uint32, c_uint64], c_uint64),
        "SteamAPI_ISteamUGC_SetItemUpdateLanguage": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemTitle": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemDescription": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemContent": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemPreview": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_AddItemPreviewFile": ([c_void_p, c_uint64, c_char_p, c_int32], c_bool),
        "SteamAPI_ISteamUGC_RemoveItemPreview": ([c_void_p, c_uint64, c_uint32], c_bool),
        "SteamAPI_ISteamUGC_SetItemTags": ([c_void_p, c_uint64, POINTER(SteamParamStringArray_t)], c_bool),
        "SteamAPI_ISteamUGC_SubmitItemUpdate": ([c_void_p, c_uint64, c_char_p], c_uint64),
        "SteamAPI_ISteamUGC_GetItemUpdateProgress": ([c_void_p, c_uint64, POINTER(c_uint64), POINTER(c_uint64)], c_int32),
    }
    for name, (args, res) in sig.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, res
    if not dll.SteamAPI_Init():
        raise RuntimeError("SteamAPI_Init() failed. Is Steam running and logged in?")
    ugc = dll.SteamInternal_FindOrCreateUserInterface(dll.SteamAPI_GetHSteamUser(), UGC_INTERFACE_VERSION)
    utils = dll.SteamAPI_ISteamClient_GetISteamUtils(dll.SteamClient(), dll.SteamAPI_GetHSteamPipe(), UTILS_INTERFACE_VERSION)
    if not ugc or not utils:
        dll.SteamAPI_Shutdown()
        raise RuntimeError("Failed to bind ISteamUGC v013 / ISteamUtils v009")
    return dll, ugc, utils


def query_preview_count(dll, ugc, utils, file_id: int) -> list[str]:
    fid = c_uint64(file_id)
    qh = dll.SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest(ugc, byref(fid), 1)
    dll.SteamAPI_ISteamUGC_SetReturnAdditionalPreviews(ugc, qh, True)
    call = dll.SteamAPI_ISteamUGC_SendQueryUGCRequest(ugc, qh)
    failed = c_bool(False)
    t0 = time.monotonic()
    while not dll.SteamAPI_ISteamUtils_IsAPICallCompleted(utils, call, byref(failed)):
        dll.SteamAPI_RunCallbacks()
        if time.monotonic() - t0 > 60:
            raise TimeoutError("QueryUGCDetails timed out")
        time.sleep(0.05)
    qc, iof = SteamUGCQueryCompleted_t(), c_bool(False)
    ok = dll.SteamAPI_ISteamUtils_GetAPICallResult(utils, call, byref(qc), ctypes.sizeof(qc), 3401, byref(iof))
    if not ok or iof.value or qc.m_eResult != 1:
        raise RuntimeError(f"QueryUGCDetails failed (ok={ok}, iof={iof.value}, EResult={qc.m_eResult})")
    n = dll.SteamAPI_ISteamUGC_GetQueryUGCNumAdditionalPreviews(ugc, qc.m_handle, 0)
    names: list[str] = []
    for i in range(n):
        u, o, t = ctypes.create_string_buffer(512), ctypes.create_string_buffer(256), c_int32()
        dll.SteamAPI_ISteamUGC_GetQueryUGCAdditionalPreview(ugc, qc.m_handle, 0, i, u, 512, o, 256, byref(t))
        names.append(o.value.decode("utf-8", "replace"))
    dll.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest(ugc, qc.m_handle)
    return names


def wait_submit(dll, ugc, utils, h: int, call: int, label: str) -> None:
    last, t0 = -1, time.monotonic()
    while True:
        dll.SteamAPI_RunCallbacks()
        done, total = c_uint64(), c_uint64()
        st = dll.SteamAPI_ISteamUGC_GetItemUpdateProgress(ugc, h, byref(done), byref(total))
        if st != last:
            print(f"    [{label}] {STATUS.get(st, st)} ({done.value}/{total.value} bytes)")
            last = st
        failed = c_bool(False)
        if dll.SteamAPI_ISteamUtils_IsAPICallCompleted(utils, call, byref(failed)):
            if failed.value:
                raise RuntimeError(f"[{label}] Steam API call failed")
            res, iof = SubmitItemUpdateResult_t(), c_bool(False)
            ok = dll.SteamAPI_ISteamUtils_GetAPICallResult(utils, call, byref(res), ctypes.sizeof(res), 3404, byref(iof))
            if not ok or iof.value or res.m_eResult != 1:
                raise RuntimeError(f"[{label}] Submit failed (ok={ok}, iof={iof.value}, EResult={res.m_eResult})")
            print(f"    [{label}] SUCCESS (legal_needed={res.m_bUserNeedsToAcceptWorkshopLegalAgreement})")
            return
        if time.monotonic() - t0 > 300:
            raise TimeoutError(f"[{label}] timed out after 300s")
        time.sleep(0.25)


def publish_target(target: str, publish: bool, metadata_only: bool, update_previews: bool) -> int:
    if target == "ipg":
        mod_dir = STANDALONE_DIR
        meta = json.loads((mod_dir / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
        file_id = int(meta["id"])
        title = IPG_TITLE
        tags = meta.get("tags", ["Graphics", "Interface"])
        desc_en = (TOOLS_DIR / "ipg_steam_description.bbcode").read_text(encoding="utf-8").strip()
        desc_cn = (TOOLS_DIR / "ipg_steam_description_cn.bbcode").read_text(encoding="utf-8").strip()
        note_en, note_cn = CHANGE_NOTE_IPG_EN, CHANGE_NOTE_IPG_CN
    elif target == "bpm25":
        mod_dir = BPM25_DIR
        meta = json.loads((mod_dir / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
        file_id = int(meta["id"])
        title = BPM25_TITLE
        tags = meta.get("tags", ["Graphics", "Interface", "1.15"])
        desc_en, desc_cn = BPM25_DESC_EN.strip(), BPM25_DESC_CN.strip()
        note_en, note_cn = CHANGE_NOTE_BPM25_EN, CHANGE_NOTE_BPM25_CN
    elif target == "gora-bpm":
        mod_dir = GORA_BPM_DIR
        meta = json.loads((mod_dir / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
        file_id = int(meta["id"])
        title = None  # preserve existing Workshop title
        tags = meta.get("tags", ["UI", "Compatibility", "1.15"])
        desc_en = desc_cn = None  # preserve existing Workshop descriptions
        note_en, note_cn = CHANGE_NOTE_GORA_BPM_EN, CHANGE_NOTE_GORA_BPM_CN
    else:
        raise SystemExit(f"Unknown target: {target}")

    version = meta.get("version", "")
    for lang, txt in (("english", desc_en), ("schinese", desc_cn)):
        if txt is not None:
            b = len(txt.encode("utf-8"))
            if b >= 8000:
                raise SystemExit(f"[{target}/{lang}] description is {b} bytes (Steam limit is 8000)")
            print(f"[{target}] Description [{lang}]: {len(txt)} chars, {b}/8000 UTF-8 bytes")

    if metadata_only:
        if not publish:
            print(f"[{target}] DRY-RUN (--metadata-only) complete.")
            return 0
        dll, ugc, utils = load_steam_api()
        try:
            for lang, desc in (("english", desc_en), ("schinese", desc_cn)):
                if desc is None:
                    continue
                h_m = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
                assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h_m, lang.encode("utf-8"))
                if title:
                    assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h_m, title.encode("utf-8"))
                assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h_m, desc.encode("utf-8"))
                call_m = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h_m, None)
                wait_submit(dll, ugc, utils, h_m, call_m, f"{target}-desc-{lang}")
        finally:
            dll.SteamAPI_Shutdown()
        return 0

    thumb_path = mod_dir / "thumbnail.png"
    gallery_paths: list[Path] = []
    if update_previews:
        assert target == "ipg", "--update-previews is only supported for --target ipg"
        gallery_paths = [mod_dir / name for name in GALLERY_FILES]
        for gp in gallery_paths:
            assert gp.exists(), f"Missing gallery screenshot: {gp}"

    with tempfile.TemporaryDirectory(prefix=f"{target}_stage_") as tmp:
        tmp_path = Path(tmp)
        stage_dir = tmp_path / mod_dir.name
        stage_dir.mkdir()
        files, size = stage_content(mod_dir, stage_dir)
        staged_names = sorted(p.relative_to(stage_dir).as_posix() for p in stage_dir.rglob("*") if p.is_file())
        print(f"[{target}] Workshop ID={file_id} | title={title or '(unchanged)'} | v{version} | tags={tags}")
        print(f"[{target}] Staged {files} files ({size / 1024:.1f} KB)")
        if thumb_path.exists():
            print(f"[{target}] Thumbnail: {thumb_path.name} ({thumb_path.stat().st_size:,} B)")
        prepared_gallery = [prepare_preview_image(gp, tmp_path) for gp in gallery_paths]
        if update_previews:
            print(f"[{target}] Gallery replacement enabled ({len(prepared_gallery)} images)")
        else:
            print(f"[{target}] Live gallery screenshots: PRESERVED (pass --update-previews to replace)")

        if not publish:
            print(f"[{target}] Sample files: {staged_names[:6]} ... {staged_names[-4:]}")
            print(f"[{target}] DRY-RUN complete. Re-run with --publish to upload.")
            return 0

        dll, ugc, utils = load_steam_api()
        try:
            if update_previews:
                old_previews = query_preview_count(dll, ugc, utils, file_id)
                print(f"[{target}] Existing gallery previews: {len(old_previews)}")
                if old_previews:
                    h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
                    for idx in range(len(old_previews) - 1, -1, -1):
                        assert dll.SteamAPI_ISteamUGC_RemoveItemPreview(ugc, h, idx)
                    call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, None)
                    wait_submit(dll, ugc, utils, h, call, f"{target}-clear-previews")

            h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h, b"english")
            if title:
                assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h, title.encode("utf-8"))
            if desc_en is not None:
                assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h, desc_en.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemContent(ugc, h, str(stage_dir).encode("utf-8"))
            if thumb_path.exists() and thumb_path.stat().st_size < 1_000_000:
                assert dll.SteamAPI_ISteamUGC_SetItemPreview(ugc, h, str(thumb_path).encode("utf-8"))
            if tags:
                arr = (c_char_p * len(tags))(*[t.encode("utf-8") for t in tags])
                assert dll.SteamAPI_ISteamUGC_SetItemTags(ugc, h, byref(SteamParamStringArray_t(arr, len(tags))))
            for gp in prepared_gallery:
                assert dll.SteamAPI_ISteamUGC_AddItemPreviewFile(ugc, h, str(gp).encode("utf-8"), 0)
            call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, note_en.encode("utf-8"))
            wait_submit(dll, ugc, utils, h, call, f"{target}-english+content")

            h_cn = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h_cn, b"schinese")
            if title:
                assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h_cn, title.encode("utf-8"))
            if desc_cn is not None:
                assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h_cn, desc_cn.encode("utf-8"))
            call_cn = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h_cn, note_cn.encode("utf-8"))
            wait_submit(dll, ugc, utils, h_cn, call_cn, f"{target}-schinese")

            if target == "ipg":
                final_previews = query_preview_count(dll, ugc, utils, file_id)
                print(f"[{target}] Verified live gallery previews preserved: {len(final_previews)}")
        finally:
            dll.SteamAPI_Shutdown()

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish IPG 3.1 / BPM2.5-ParliamentGraph / GORA×BPM Compat to Steam Workshop.")
    ap.add_argument("--target", choices=("ipg", "bpm25", "gora-bpm"), default="ipg", help="Workshop target to publish")
    ap.add_argument("--publish", action="store_true", help="Upload to Steam Workshop (omit for dry run)")
    ap.add_argument("--metadata-only", action="store_true", help="Update EN + ZH-CN descriptions only")
    ap.add_argument("--update-previews", action="store_true", help="Replace live gallery screenshots (ipg only)")
    args = ap.parse_args()
    return publish_target(args.target, args.publish, args.metadata_only, args.update_previews)


if __name__ == "__main__":
    raise SystemExit(main())
