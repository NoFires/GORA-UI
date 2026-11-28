"""Steam Workshop publisher for standalone Victorian Charts via Steamworks C-API.

Supports creating a new Workshop item automatically when `.metadata/metadata.json`
does not yet contain a numeric Steam PublishedFileId, then updates content, preview,
gallery comparison screenshot, tags, visibility (Public), and bilingual EN + ZH-CN
descriptions. Stages ONLY pure mod files (`.metadata/metadata.json`, `gfx/FX/*.shader`,
`thumbnail.png`) so the Workshop folder stays 100% pure with zero tool scripts.

Default is a dry run; pass `--publish` to create/upload.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import tempfile
import time
from ctypes import POINTER, Structure, byref, c_bool, c_char_p, c_int32, c_uint32, c_uint64, c_void_p
from pathlib import Path

APP_ID = 529340
UGC_INTERFACE_VERSION = b"STEAMUGC_INTERFACE_VERSION013"
UTILS_INTERFACE_VERSION = b"SteamUtils009"
K_EWORKSHOP_FILE_TYPE_COMMUNITY = 0
K_EREMOTE_STORAGE_VISIBILITY_PUBLIC = 0

TOOLS_DIR = Path(__file__).resolve().parent
MODS_ROOT = TOOLS_DIR.parent.parent
VC_DIR = MODS_ROOT / "Victorian Charts"
STEAM_DLL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\binaries\steam_api64_o.dll")

PURE_REL_FILES = [
    Path(".metadata/metadata.json"),
    Path("gfx/FX/pdxgui_piechart.shader"),
    Path("gfx/FX/pdxgui_treemapchart.shader"),
    Path("thumbnail.png"),
]

TITLE_EN = "Victorian Charts"
TITLE_CN = "Victorian Charts — 维多利亚复古图表"

DESC_EN = """Makes all pie charts and treemap charts in the game look cleaner and more consistent with Victoria 3's art style: softer contrast, subtle texture, and crisp 1px dark borders between slices.

[h2]Compatibility[/h2]
[list]
[*]Only modifies [b]gfx/FX/pdxgui_piechart.shader[/b] and [b]gfx/FX/pdxgui_treemapchart.shader[/b].
[*]Compatible with all mods that do not modify those two files.
[*]Ironman, Achievement, and Multiplayer safe.
[*]Already included in [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3724865565]GORA UI+[/url].
[/list]"""

DESC_CN = """统一优化游戏内所有饼图和树图的美术观感：适当降低刺眼对比度，增加柔和质感与 1px 暗线分隔，更贴合《维多利亚 3》整体画风。

[h2]兼容性[/h2]
[list]
[*]仅修改 [b]gfx/FX/pdxgui_piechart.shader[/b] 与 [b]gfx/FX/pdxgui_treemapchart.shader[/b]。
[*]兼容所有不修改上述两个文件的 Mod。
[*]支持成就、铁人与联机，不改校验和。
[*]已同步整合至 [url=https://steamcommunity.com/sharedfiles/filedetails/?id=3724865565]GORA UI+[/url]。
[/list]"""

NOTE_EN = "v1.0.0 — Initial release: Universal pure gfx/FX Victorian antique shader overhaul for all Pie Charts and Treemap Charts (zero GUI conflicts, MP & Achievement safe)."
NOTE_CN = "v1.0.0 — 首次发布：纯 gfx/FX 着色器实现的全局通用维多利亚复古饼图与树图美化（零 GUI 冲突、联机与成就安全）。"

STATUS = {
    0: "Invalid", 1: "PreparingConfig", 2: "PreparingContent",
    3: "UploadingContent", 4: "UploadingPreviewFile", 5: "CommittingChanges",
}


class CreateItemResult_t(Structure):
    _fields_ = [
        ("m_eResult", c_int32),
        ("m_nPublishedFileId", c_uint64),
        ("m_bUserNeedsToAcceptWorkshopLegalAgreement", c_bool),
    ]


class SubmitItemUpdateResult_t(Structure):
    _fields_ = [
        ("m_eResult", c_int32),
        ("m_bUserNeedsToAcceptWorkshopLegalAgreement", c_bool),
        ("m_nPublishedFileId", c_uint64),
    ]


class SteamParamStringArray_t(Structure):
    _fields_ = [("m_ppStrings", POINTER(c_char_p)), ("m_nNumStrings", c_int32)]


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
        "SteamAPI_ISteamUGC_CreateItem": ([c_void_p, c_uint32, c_int32], c_uint64),
        "SteamAPI_ISteamUGC_StartItemUpdate": ([c_void_p, c_uint32, c_uint64], c_uint64),
        "SteamAPI_ISteamUGC_SetItemUpdateLanguage": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemTitle": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemDescription": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemVisibility": ([c_void_p, c_uint64, c_int32], c_bool),
        "SteamAPI_ISteamUGC_SetItemContent": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemPreview": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_AddItemPreviewFile": ([c_void_p, c_uint64, c_char_p, c_int32], c_bool),
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


def create_workshop_item(dll, ugc, utils) -> int:
    call = dll.SteamAPI_ISteamUGC_CreateItem(ugc, APP_ID, K_EWORKSHOP_FILE_TYPE_COMMUNITY)
    failed = c_bool(False)
    t0 = time.monotonic()
    while not dll.SteamAPI_ISteamUtils_IsAPICallCompleted(utils, call, byref(failed)):
        dll.SteamAPI_RunCallbacks()
        if time.monotonic() - t0 > 60:
            raise TimeoutError("CreateItem timed out")
        time.sleep(0.05)
    if failed.value:
        raise RuntimeError("CreateItem Steam API call failed")
    res, iof = CreateItemResult_t(), c_bool(False)
    ok = dll.SteamAPI_ISteamUtils_GetAPICallResult(utils, call, byref(res), ctypes.sizeof(res), 3403, byref(iof))
    if not ok or iof.value or res.m_eResult != 1 or not res.m_nPublishedFileId:
        raise RuntimeError(f"CreateItem failed (ok={ok}, iof={iof.value}, EResult={res.m_eResult}, id={res.m_nPublishedFileId})")
    print(f"    [CreateItem] Created Workshop ID={res.m_nPublishedFileId} (legal_needed={res.m_bUserNeedsToAcceptWorkshopLegalAgreement})")
    return int(res.m_nPublishedFileId)


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
            print(f"    [{label}] SUCCESS (id={res.m_nPublishedFileId}, legal_needed={res.m_bUserNeedsToAcceptWorkshopLegalAgreement})")
            return
        if time.monotonic() - t0 > 300:
            raise TimeoutError(f"[{label}] timed out after 300s")
        time.sleep(0.25)


def stage_pure_mod(dst: Path) -> list[str]:
    staged = []
    for rel in PURE_REL_FILES:
        src = VC_DIR / rel
        if not src.exists():
            raise FileNotFoundError(f"Missing required pure mod file: {src}")
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        staged.append(rel.as_posix())
    return staged


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish standalone Victorian Charts to Steam Workshop.")
    ap.add_argument("--publish", action="store_true", help="Create/upload to Steam Workshop (omit for dry run)")
    ap.add_argument("--metadata-only", action="store_true", help="Update EN + ZH-CN titles/descriptions only")
    ap.add_argument("--gallery", action="append", default=[], help="Optional extra preview image path(s) for Workshop gallery")
    args = ap.parse_args()

    meta_path = VC_DIR / ".metadata" / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    raw_id = str(meta.get("id", ""))
    file_id = int(raw_id) if raw_id.isdigit() else 0
    tags = meta.get("tags", ["Graphics", "Interface"])
    if "1.15" not in tags:
        tags = list(tags) + ["1.15"]

    for lang, txt in (("english", DESC_EN.strip()), ("schinese", DESC_CN.strip())):
        b = len(txt.encode("utf-8"))
        assert b < 8000, f"[{lang}] description too long ({b} bytes)"
        print(f"[vc] Description [{lang}]: {len(txt)} chars, {b}/8000 bytes")

    if args.metadata_only:
        assert file_id > 0, "Cannot use --metadata-only before Workshop item is created"
        if not args.publish:
            print(f"[vc] DRY-RUN (--metadata-only) for Workshop ID={file_id} complete.")
            return 0
        dll, ugc, utils = load_steam_api()
        try:
            for lang, ttl, desc in (("english", TITLE_EN, DESC_EN.strip()), ("schinese", TITLE_CN, DESC_CN.strip())):
                h_m = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
                assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h_m, lang.encode("utf-8"))
                assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h_m, ttl.encode("utf-8"))
                assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h_m, desc.encode("utf-8"))
                call_m = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h_m, None)
                wait_submit(dll, ugc, utils, h_m, call_m, f"vc-desc-{lang}")
        finally:
            dll.SteamAPI_Shutdown()
        return 0

    thumb_path = VC_DIR / "thumbnail.png"
    assert thumb_path.exists(), f"Missing thumbnail: {thumb_path}"
    assert thumb_path.stat().st_size < 1_000_000, f"Thumbnail exceeds 1 MB: {thumb_path.stat().st_size}"

    gallery_paths = [Path(p) for p in args.gallery]
    for gp in gallery_paths:
        assert gp.exists(), f"Missing gallery image: {gp}"
        assert gp.stat().st_size < 1_000_000, f"Gallery image exceeds 1 MB: {gp}"

    with tempfile.TemporaryDirectory(prefix="vc_stage_") as tmp:
        stage_dir = Path(tmp) / "Victorian Charts"
        stage_dir.mkdir()
        staged = stage_pure_mod(stage_dir)
        total_bytes = sum((stage_dir / r).stat().st_size for r in staged)
        print(f"[vc] Existing Workshop ID={file_id or '(NEW — will call CreateItem)'} | v{meta.get('version')} | tags={tags}")
        print(f"[vc] Pure staged files ({len(staged)}, {total_bytes / 1024:.1f} KB): {staged}")
        print(f"[vc] Thumbnail: {thumb_path.name} ({thumb_path.stat().st_size:,} B)")
        if gallery_paths:
            print(f"[vc] Extra gallery previews: {[p.name for p in gallery_paths]}")

        if not args.publish:
            print("[vc] DRY-RUN complete. Re-run with --publish to create/upload.")
            return 0

        dll, ugc, utils = load_steam_api()
        try:
            is_new = file_id == 0
            if is_new:
                file_id = create_workshop_item(dll, ugc, utils)
                # Persist numeric Steam Workshop ID back into metadata.json and staged copy
                meta["id"] = str(file_id)
                meta_text = json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
                meta_path.write_text(meta_text, encoding="utf-8")
                (stage_dir / ".metadata" / "metadata.json").write_text(meta_text, encoding="utf-8")

            h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h, b"english")
            assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h, TITLE_EN.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h, DESC_EN.strip().encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemVisibility(ugc, h, K_EREMOTE_STORAGE_VISIBILITY_PUBLIC)
            assert dll.SteamAPI_ISteamUGC_SetItemContent(ugc, h, str(stage_dir).encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemPreview(ugc, h, str(thumb_path).encode("utf-8"))
            arr = (c_char_p * len(tags))(*[t.encode("utf-8") for t in tags])
            assert dll.SteamAPI_ISteamUGC_SetItemTags(ugc, h, byref(SteamParamStringArray_t(arr, len(tags))))
            for gp in gallery_paths:
                assert dll.SteamAPI_ISteamUGC_AddItemPreviewFile(ugc, h, str(gp).encode("utf-8"), 0)
            call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, NOTE_EN.encode("utf-8"))
            wait_submit(dll, ugc, utils, h, call, "vc-english+content")

            h_cn = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h_cn, b"schinese")
            assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h_cn, TITLE_CN.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h_cn, DESC_CN.strip().encode("utf-8"))
            call_cn = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h_cn, NOTE_CN.encode("utf-8"))
            wait_submit(dll, ugc, utils, h_cn, call_cn, "vc-schinese")

            print(f"\n[vc] PUBLISHED: https://steamcommunity.com/sharedfiles/filedetails/?id={file_id}")
        finally:
            dll.SteamAPI_Shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
