"""Steam Workshop publisher for GORA UI+ (adapted from V3-Navy-Mod/tools/publish_steam.py).

Talks to the running Steam client through the Steamworks C-API shipped with Victoria 3.
Default is a dry run (stage + preview). Pass --publish to upload.

Change notes and descriptions are per language: the content upload carries the
English description (tools/steam_description.bbcode) and change note
(CHANGELOG.md), then a content-less update tagged schinese carries the Chinese
description (tools/steam_description_cn.bbcode) and change note
(CHANGELOG_CN.md). Each changelog's top "## [x.y.z]" section is used.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import sys
import tempfile
import time
from ctypes import POINTER, Structure, byref, c_bool, c_char_p, c_int32, c_uint32, c_uint64, c_void_p
from pathlib import Path

APP_ID = 529340
UGC_INTERFACE_VERSION = b"STEAMUGC_INTERFACE_VERSION013"
UTILS_INTERFACE_VERSION = b"SteamUtils009"

MOD_DIR = Path(__file__).resolve().parent.parent
# The game's steam_api64.dll is a wrapper; the _o copy is the real Steamworks DLL.
STEAM_DLL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\binaries\steam_api64_o.dll")
INCLUDE = [".metadata", "common", "data_binding", "events", "gfx", "gui", "input_profile",
           "localization", "README.md", "reference.md", "thumbnail.png"]

STATUS = {0: "Invalid", 1: "PreparingConfig", 2: "PreparingContent", 3: "UploadingContent",
          4: "UploadingPreviewFile", 5: "CommittingChanges"}


class SubmitItemUpdateResult_t(Structure):
    _fields_ = [("m_eResult", c_int32),
                ("m_bUserNeedsToAcceptWorkshopLegalAgreement", c_bool),
                ("m_nPublishedFileId", c_uint64)]


class SteamParamStringArray_t(Structure):
    _fields_ = [("m_ppStrings", POINTER(c_char_p)), ("m_nNumStrings", c_int32)]


def latest_changelog(path: Path, version: str) -> str:
    """Top '## [x]' section as plain text; refuses to publish a note for another version.

    Plain text on purpose: BBCode ([b], [list]) renders each part in a different style on
    the Workshop change notes page.
    """
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## \[(.+?)\][^\n]*\n(.*?)(?=^## \[|\Z)", text, flags=re.M | re.S)
    if not m:
        raise SystemExit(f"No '## [version]' section in {path.name}")
    if m.group(1) != version:
        raise SystemExit(f"{path.name} top section is {m.group(1)}, metadata version is {version}")
    body = re.sub(r"\*\*([^*]+)\*\*|`([^`]+)`", lambda x: x.group(1) or x.group(2), m.group(2).strip())
    return f"v{version}\n{body}"


def stage(dst: Path) -> tuple[int, int]:
    files = size = 0
    for entry in INCLUDE:
        src = MOD_DIR / entry
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst / entry, ignore=shutil.ignore_patterns(".omc", "__pycache__"))
        else:
            shutil.copy2(src, dst / entry)
    for p in dst.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return files, size


def load_steam_api():
    if not STEAM_DLL.exists():
        raise FileNotFoundError(f"Steamworks DLL not found: {STEAM_DLL}")
    os.environ["SteamAppId"] = os.environ["SteamGameId"] = str(APP_ID)
    dll = ctypes.CDLL(str(STEAM_DLL))
    sig = {
        "SteamAPI_Init": ([], c_bool), "SteamAPI_Shutdown": ([], None), "SteamAPI_RunCallbacks": ([], None),
        "SteamAPI_GetHSteamUser": ([], c_int32), "SteamAPI_GetHSteamPipe": ([], c_int32), "SteamClient": ([], c_void_p),
        "SteamInternal_FindOrCreateUserInterface": ([c_int32, c_char_p], c_void_p),
        "SteamAPI_ISteamClient_GetISteamUtils": ([c_void_p, c_int32, c_char_p], c_void_p),
        "SteamAPI_ISteamUtils_IsAPICallCompleted": ([c_void_p, c_uint64, POINTER(c_bool)], c_bool),
        "SteamAPI_ISteamUtils_GetAPICallResult": ([c_void_p, c_uint64, c_void_p, c_int32, c_int32, POINTER(c_bool)], c_bool),
        "SteamAPI_ISteamUGC_StartItemUpdate": ([c_void_p, c_uint32, c_uint64], c_uint64),
        "SteamAPI_ISteamUGC_SetItemUpdateLanguage": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemTitle": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemDescription": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemContent": ([c_void_p, c_uint64, c_char_p], c_bool),
        "SteamAPI_ISteamUGC_SetItemTags": ([c_void_p, c_uint64, POINTER(SteamParamStringArray_t)], c_bool),
        "SteamAPI_ISteamUGC_SubmitItemUpdate": ([c_void_p, c_uint64, c_char_p], c_uint64),
        "SteamAPI_ISteamUGC_GetItemUpdateProgress": ([c_void_p, c_uint64, POINTER(c_uint64), POINTER(c_uint64)], c_int32),
    }
    for name, (args, res) in sig.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, res
    if not dll.SteamAPI_Init():
        raise RuntimeError("SteamAPI_Init() failed. Is the Steam client running and logged in?")
    ugc = dll.SteamInternal_FindOrCreateUserInterface(dll.SteamAPI_GetHSteamUser(), UGC_INTERFACE_VERSION)
    utils = dll.SteamAPI_ISteamClient_GetISteamUtils(dll.SteamClient(), dll.SteamAPI_GetHSteamPipe(), UTILS_INTERFACE_VERSION)
    if not ugc or not utils:
        dll.SteamAPI_Shutdown()
        raise RuntimeError("Failed to bind ISteamUGC v013 / ISteamUtils v009")
    return dll, ugc, utils


def submit(dll, ugc, utils, file_id: int, lang: str, note: str | None, title: str | None = None,
           description: str | None = None, content: Path | None = None, tags: list[str] = ()) -> None:
    h = dll.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP_ID, file_id)
    if not h:
        raise RuntimeError("StartItemUpdate returned an invalid handle")
    if not dll.SteamAPI_ISteamUGC_SetItemUpdateLanguage(ugc, h, lang.encode()):
        raise RuntimeError(f"SetItemUpdateLanguage({lang}) failed")
    if title is not None:
        if not dll.SteamAPI_ISteamUGC_SetItemTitle(ugc, h, title.encode("utf-8")):
            raise RuntimeError(f"SetItemTitle({lang}) failed")
    if description is not None:
        desc_bytes = description.encode("utf-8")
        if len(desc_bytes) >= 8000:
            raise ValueError(f"[{lang}] description is {len(desc_bytes)} bytes (Steam limit is 8000)")
        if not dll.SteamAPI_ISteamUGC_SetItemDescription(ugc, h, desc_bytes):
            raise RuntimeError(f"SetItemDescription({lang}) failed")
    if content and not dll.SteamAPI_ISteamUGC_SetItemContent(ugc, h, str(content).encode()):
        raise RuntimeError(f"SetItemContent({content}) failed")
    if tags:
        arr = (c_char_p * len(tags))(*[t.encode() for t in tags])
        if not dll.SteamAPI_ISteamUGC_SetItemTags(ugc, h, byref(SteamParamStringArray_t(arr, len(tags)))):
            raise RuntimeError("SetItemTags failed")
    call = dll.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, note.encode("utf-8") if note is not None else None)
    if not call:
        raise RuntimeError("SubmitItemUpdate returned 0")

    last, t0 = -1, time.monotonic()
    while True:
        dll.SteamAPI_RunCallbacks()
        done, total = c_uint64(), c_uint64()
        st = dll.SteamAPI_ISteamUGC_GetItemUpdateProgress(ugc, h, byref(done), byref(total))
        if st != last:
            print(f"    [{lang}] {STATUS.get(st, st)} ({done.value}/{total.value} bytes)")
            last = st
        failed = c_bool(False)
        if dll.SteamAPI_ISteamUtils_IsAPICallCompleted(utils, call, byref(failed)):
            if failed.value:
                raise RuntimeError("Steam API call failed")
            res, io_failed = SubmitItemUpdateResult_t(), c_bool(False)
            # 3404 = k_iClientUGCCallbacks (3400) + 4 -> SubmitItemUpdateResult_t
            ok = dll.SteamAPI_ISteamUtils_GetAPICallResult(utils, call, byref(res), ctypes.sizeof(res), 3404, byref(io_failed))
            if not ok or io_failed.value or res.m_eResult != 1:
                raise RuntimeError(f"Workshop update failed (ok={ok}, io_failed={io_failed.value}, EResult={res.m_eResult})")
            print(f"    [{lang}] SUCCESS (legal_agreement_needed={res.m_bUserNeedsToAcceptWorkshopLegalAgreement})")
            return
        if time.monotonic() - t0 > 300:
            raise TimeoutError("Workshop upload timed out after 300s")
        time.sleep(0.25)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage and publish GORA UI+ to Steam Workshop.")
    ap.add_argument("--publish", action="store_true", help="Upload (omit for dry run)")
    ap.add_argument("--no-description", action="store_true", help="Skip updating Workshop descriptions")
    ap.add_argument("--metadata-only", action="store_true", help="Update title/description only (no content or change notes)")
    args = ap.parse_args()

    meta = json.loads((MOD_DIR / ".metadata" / "metadata.json").read_text(encoding="utf-8-sig"))
    file_id, title, version, tags = int(meta["id"]), meta["name"], meta["version"], meta.get("tags", [])
    notes = {"english": latest_changelog(MOD_DIR / "CHANGELOG.md", version),
             "schinese": latest_changelog(MOD_DIR / "CHANGELOG_CN.md", version)}
    desc_paths = {"english": MOD_DIR / "tools" / "steam_description.bbcode",
                  "schinese": MOD_DIR / "tools" / "steam_description_cn.bbcode"}
    descs: dict[str, str | None] = {}
    for lang, p in desc_paths.items():
        if args.no_description or not p.exists():
            descs[lang] = None
        else:
            txt = p.read_text(encoding="utf-8").strip()
            b = len(txt.encode("utf-8"))
            if b >= 8000:
                raise SystemExit(f"{p.name} is {b} UTF-8 bytes (Steam limit is 8000)")
            descs[lang] = txt

    with tempfile.TemporaryDirectory(prefix="gora_stage_") as tmp:
        stage_dir = Path(tmp) / "GORA UI+"
        stage_dir.mkdir()
        files, size = stage(stage_dir)
        print(f"Workshop ID={file_id} | v{version} | tags={tags}")
        print(f"Staged {files} files, {size / 1024:.1f} KB")
        for lang, desc in descs.items():
            if desc is not None:
                print(f"Description [{lang}]: {len(desc)} chars, {len(desc.encode('utf-8'))}/8000 UTF-8 bytes")
        for lang, note in notes.items():
            print(f"--- change note [{lang}] ---\n{note}\n")
        if not args.publish:
            print("DRY-RUN complete. Re-run with --publish to upload.")
            return 0

        dll, ugc, utils = load_steam_api()
        try:
            if args.metadata_only:
                for lang in ("english", "schinese"):
                    submit(dll, ugc, utils, file_id, lang, None, title=title, description=descs[lang])
            else:
                submit(dll, ugc, utils, file_id, "english", notes["english"],
                       title=title if descs["english"] is not None else None,
                       description=descs["english"], content=stage_dir, tags=tags)
                submit(dll, ugc, utils, file_id, "schinese", notes["schinese"],
                       title=title if descs["schinese"] is not None else None,
                       description=descs["schinese"])
        finally:
            dll.SteamAPI_Shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
