"""Steam Workshop publisher for standalone Improved ParliamentGraph[1.15] (ID 3721626337).

Uses the real Steamworks C-API (steam_api64_o.dll) shipped with Victoria 3.
Supports:
  - Clean mod content staging (excludes showcase PNGs, _build_*.py, __pycache__, dot-files except .metadata)
  - Updating the Workshop avatar / thumbnail via SetItemPreview (thumbnail.png)
  - Deleting ALL existing gallery screenshots before uploading the curated v3.0 gallery set
  - Bilingual English + Simplified Chinese Workshop descriptions and v3.0.0 change notes
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
from ctypes import POINTER, Structure, byref, c_bool, c_char, c_char_p, c_float, c_int32, c_uint32, c_uint64, c_void_p
from pathlib import Path

APP_ID = 529340
UGC_INTERFACE_VERSION = b"STEAMUGC_INTERFACE_VERSION013"
UTILS_INTERFACE_VERSION = b"SteamUtils009"

TOOLS_DIR = Path(__file__).resolve().parent
STANDALONE_DIR = TOOLS_DIR.parent.parent / "Improved ParliamentGraph[1.15]"
STEAM_DLL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\binaries\steam_api64_o.dll")

ALLOWED_DOT_ENTRIES = {".metadata"}
EXCLUDE_NAMES = {"__pycache__", "build", "_build_localization.py", "_build_seat_layout.py"}

# Ordered showcase screenshots (10 gallery images; thumbnail.png is set via SetItemPreview)
GALLERY_FILES = [
    "1.png",
    "2.png",
    "3.png",
    "4.png",
    "5.png",
    "Westminster.png",
    "Hemicyle.png",
    "Hourshoe.png",
    "Assembly.png",
    "Bicameral.png",
]

CHANGE_NOTE_EN = """v3.0.0 — Major Overhaul!
- 5 authentic chamber architectures (Westminster, Bicameral Split, Commonwealth Horseshoe, Terraced Assembly Hall, Classic Hemicycle) with culture & law smart auto-matching (British/Anglo-Canadian -> Westminster, Presidential Republic -> Bicameral, Council/Single-Party -> Assembly, Australian/Constitutional Monarchy -> Horseshoe)
- Sleek bottom-right layout selector button + dropdown popup with native FancyTooltips explaining your active chamber, match reason, and every layout's auto-match condition
- Dynamic real seat counts (50–650 seats) scaling with franchise law, incorporated states, and politically active population, apportioned via Hamilton (largest-remainder) method across 100/200/300 visual tiers
- Completely redesigned Paradox-native FancyTooltips with ornate emblems, multi-color stacked parliament bars, 50% electoral majority needle, and grouped In Government / In Opposition zebra-striped tables
- Interactive per-seat hover tooltips on every seat dot, gold coalition halos, Head of State focal seat, and instant updates on government reform
- Updated all 11 official languages"""

CHANGE_NOTE_CN = """v3.0.0 — 史诗级大更新！
- 新增 5 大历史议会形态（威斯敏斯特对座式、两院分席、马蹄形、阶梯大会堂、经典半圆）并支持按文化传统与政体法律智能自动匹配（英国系文化 -> 威斯敏斯特、总统共和 -> 两院分席、委员会/一党制 -> 大会堂、澳大利亚/君主立宪 -> 马蹄形）
- 画布右下角新增紧凑布局选择按钮与原生下拉菜单，悬停即可通过原版徽章提示框查看当前结构、匹配原因及各样式触发条件
- 席位总数支持 50–650 席动态变化（随权力分配法律、已整合州数与活跃人口比例演化），采用哈密顿最大余数法精确分配
- 全面重做 4 个主提示框：原版徽章标题栏、多色比例堆叠进度条（政党结构含 50% 过半线）、执政/在野原生图标分组斑马纹表格
- 支持画布单席位圆点悬停提示、执政金色外环、国家元首专属主位及政府改组即时刷新
- 完整同步全部 11 种官方语言本地化"""

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


def _ignore_entries(src_dir: str, names: list[str]) -> set[str]:
    is_root = Path(src_dir).resolve() == STANDALONE_DIR.resolve()
    ignored: set[str] = set()
    for name in names:
        if name.startswith(".") and not (is_root and name in ALLOWED_DOT_ENTRIES):
            ignored.add(name)
        elif name in EXCLUDE_NAMES or name.endswith(".pyc"):
            ignored.add(name)
        elif is_root and name.lower().endswith(".png") and name != "thumbnail.png":
            ignored.add(name)
    return ignored


def stage_content(dst: Path) -> tuple[int, int]:
    shutil.copytree(STANDALONE_DIR, dst, ignore=_ignore_entries, dirs_exist_ok=True)
    files = size = 0
    for p in dst.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return files, size


def prepare_preview_image(src: Path, tmp_dir: Path, max_bytes: int = 980_000) -> Path:
    """Return src if already under Steam's safe size limit, else save an optimized copy in tmp_dir."""
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
            print(f"    [IMG] Compressed {src.name} ({src.stat().st_size:,} B) -> {out_jpg.name} ({out_jpg.stat().st_size:,} B, q={q})")
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish standalone Improved ParliamentGraph[1.15] v3.0 to Steam Workshop.")
    ap.add_argument("--publish", action="store_true", help="Upload to Steam Workshop (omit for dry run)")
    args = ap.parse_args()

    meta = json.loads((STANDALONE_DIR / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
    file_id = int(meta["id"])
    title = meta["name"]
    version = meta["version"]
    tags = meta.get("tags", ["Graphics", "Interface"])

    desc_en = (TOOLS_DIR / "ipg_steam_description.bbcode").read_text(encoding="utf-8").strip()
    desc_cn = (TOOLS_DIR / "ipg_steam_description_cn.bbcode").read_text(encoding="utf-8").strip()
    for lang, txt in (("english", desc_en), ("schinese", desc_cn)):
        b = len(txt.encode("utf-8"))
        if b >= 8000:
            raise SystemExit(f"[{lang}] description is {b} bytes (Steam limit is 8000)")
        print(f"Description [{lang}]: {len(txt)} chars, {b}/8000 UTF-8 bytes")

    thumb_path = STANDALONE_DIR / "thumbnail.png"
    assert thumb_path.exists(), f"Missing {thumb_path}"
    assert thumb_path.stat().st_size < 1_000_000, f"thumbnail.png exceeds 1 MB ({thumb_path.stat().st_size} B)"

    gallery_paths = [STANDALONE_DIR / name for name in GALLERY_FILES]
    for gp in gallery_paths:
        assert gp.exists(), f"Missing gallery screenshot: {gp}"

    with tempfile.TemporaryDirectory(prefix="ipg_stage_") as tmp:
        tmp_path = Path(tmp)
        stage_dir = tmp_path / "Improved ParliamentGraph[1.15]"
        stage_dir.mkdir()
        files, size = stage_content(stage_dir)
        staged_names = sorted(p.relative_to(stage_dir).as_posix() for p in stage_dir.rglob("*") if p.is_file())
        print(f"Workshop ID={file_id} | title={title} | v{version} | tags={tags}")
        print(f"Staged {files} mod files ({size / 1024:.1f} KB) — excluded all loose showcase PNGs & build scripts")
        print(f"Thumbnail: {thumb_path.name} ({thumb_path.stat().st_size:,} B)")

        prepared_gallery = [prepare_preview_image(gp, tmp_path) for gp in gallery_paths]
        print(f"Gallery ({len(prepared_gallery)} images): {[p.name for p in prepared_gallery]}")

        if not args.publish:
            print("Staged files sample:", staged_names[:10], "...", staged_names[-5:])
            print("DRY-RUN complete. Re-run with --publish to upload.")
            return 0

        dll, ugc, utils = load_steam_api()
        try:
            # Phase 1: Delete ALL existing gallery screenshots first
            old_previews = query_preview_count(dll, ugc, utils, file_id)
            print(f"[1/4] Existing gallery previews: {len(old_previews)} -> {old_previews}")
            if old_previews:
                h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
                for idx in range(len(old_previews) - 1, -1, -1):
                    ok = dll.SteamAPI_ISteamUGC_RemoveItemPreview(ugc, h, idx)
                    if not ok:
                        raise RuntimeError(f"RemoveItemPreview({idx}) returned False")
                call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, None)
                wait_submit(dll, ugc, utils, h, call, "clear-old-previews")
                remaining = query_preview_count(dll, ugc, utils, file_id)
                print(f"    Verified remaining old previews: {len(remaining)} {remaining}")

            # Phase 2: Upload v3.0.0 mod content + thumbnail + 10 new gallery screenshots + English desc & note
            print("[2/4] Uploading v3.0.0 content, thumbnail, 10 gallery screenshots, and English description...")
            h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h, b"english")
            assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h, title.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h, desc_en.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemContent(ugc, h, str(stage_dir).encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemPreview(ugc, h, str(thumb_path).encode("utf-8"))
            arr = (c_char_p * len(tags))(*[t.encode("utf-8") for t in tags])
            assert dll.SteamAPI_ISteamUGC_SetItemTags(ugc, h, byref(SteamParamStringArray_t(arr, len(tags))))
            for gp in prepared_gallery:
                # 0 = k_EItemPreviewType_Image
                assert dll.SteamAPI_ISteamUGC_AddItemPreviewFile(ugc, h, str(gp).encode("utf-8"), 0), f"AddItemPreviewFile failed for {gp}"
            call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, CHANGE_NOTE_EN.encode("utf-8"))
            wait_submit(dll, ugc, utils, h, call, "english+content+previews")

            # Phase 3: Upload Simplified Chinese description & change note
            print("[3/4] Uploading Simplified Chinese description and v3.0.0 change note...")
            h_cn = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
            assert dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h_cn, b"schinese")
            assert dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h_cn, title.encode("utf-8"))
            assert dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h_cn, desc_cn.encode("utf-8"))
            call_cn = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h_cn, CHANGE_NOTE_CN.encode("utf-8"))
            wait_submit(dll, ugc, utils, h_cn, call_cn, "schinese")

            # Phase 4: Verify final gallery state
            final_previews = query_preview_count(dll, ugc, utils, file_id)
            print(f"[4/4] Final live gallery previews ({len(final_previews)}): {final_previews}")
        finally:
            dll.SteamAPI_Shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
