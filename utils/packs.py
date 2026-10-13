"""Biome packs: export saved biomes with their assets to a .rafpack file and install packs."""
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

import bpy

from . import biomes as biomes_utils


#----CONSTANTS----
PACK_EXTENSION = ".rafpack"
PACK_FORMAT = 1
PACK_KIND = "raf_scatter_pack"
PACK_MANIFEST = "pack.json"
PACK_ASSETS_FILE = "assets/assets.blend"
PACK_ASSETS_DIR = "assets"
PACK_TEXTURE_DIR = "assets/textures"
_ASSET_LIBRARY_SUFFIX = " (RAF Pack)"
_INSTALL_PREFIX = ".installing_"
_WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "pack_worker.py")
_WORKER_TIMEOUT = 900
_SUMMARY_CACHE_SIZE = 16
_TEXT_EXTENSIONS = {".json", ".rafbiome", ".txt", ".md"}
_ALLOWED_EXTENSIONS = _TEXT_EXTENSIONS | {
    ".blend", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".hdr", ".tga", ".bmp", ".webp",
}


#----MODULE STATE----
_summary_cache = {}


#----PACK FILES----
def _validate_manifest(data):
    """Raise ValueError when manifest data does not describe a known pack."""
    if not isinstance(data, dict) or data.get("kind") != PACK_KIND:
        raise ValueError("not a RAF Scatter biome pack")
    if data.get("format") != PACK_FORMAT:
        raise ValueError("unknown pack format")
    name = data.get("name")
    if not isinstance(name, str) or not biomes_utils.sanitize_biome_name(name):
        raise ValueError("the pack has no name")


def _read_manifest(root):
    try:
        with open(os.path.join(root, PACK_MANIFEST), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as error:
        raise ValueError(str(error)) from error
    _validate_manifest(data)
    return data


def _pack_info(pack_id, root):
    try:
        manifest, valid = _read_manifest(root), True
    except ValueError:
        manifest, valid = {}, False
    return {
        "id": pack_id,
        "name": str(manifest.get("name") or pack_id),
        "version": str(manifest.get("version", "")),
        "author": str(manifest.get("author", "")),
        "valid": valid,
        "biomes": biomes_utils.list_pack_biomes(pack_id),
        "asset_library": getattr(find_pack_asset_library(root), "name", ""),
        "root": root,
    }


def list_packs():
    """Return the info of every installed pack, sorted by name."""
    folder = biomes_utils.get_packs_dir()
    if not folder or not os.path.isdir(folder):
        return []
    packs = [
        _pack_info(entry, os.path.join(folder, entry)) for entry in os.listdir(folder)
        if not entry.startswith(_INSTALL_PREFIX) and os.path.isdir(os.path.join(folder, entry))
    ]
    return sorted(packs, key=lambda info: info["name"].lower())


#----ASSET LIBRARIES----
def _normalized(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(bpy.path.abspath(path))))


def find_pack_asset_library(root):
    """Return the asset library registered for a pack's assets folder, or None."""
    target = _normalized(os.path.join(root, PACK_ASSETS_DIR))
    for library in bpy.context.preferences.filepaths.asset_libraries:
        if library.path and _normalized(library.path) == target:
            return library
    return None


def add_pack_asset_library(root, pack_name):
    """Register a pack's assets folder as an asset library unless it already is one."""
    directory = os.path.join(root, PACK_ASSETS_DIR)
    if not os.path.isdir(directory) or find_pack_asset_library(root) is not None:
        return
    preferences = bpy.context.preferences
    libraries = preferences.filepaths.asset_libraries
    libraries.new(name=pack_name + _ASSET_LIBRARY_SUFFIX, directory=directory)
    preferences.is_dirty = True


def remove_pack_asset_library(root):
    library = find_pack_asset_library(root)
    if library is None:
        return
    preferences = bpy.context.preferences
    preferences.filepaths.asset_libraries.remove(library)
    preferences.is_dirty = True


#----INSTALL----
def _member_parts(filename):
    """Return the path parts of a zip member, or None when it could leave the pack folder."""
    parts = [part for part in filename.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or ":" in part for part in parts):
        return None
    return parts


def _find_manifest(members):
    """Return (member, path parts) of the manifest at the root or one folder down, or None."""
    best = None
    for member in members:
        parts = _member_parts(member.filename)
        if not parts or parts[-1] != PACK_MANIFEST or len(parts) > 2:
            continue
        if best is None or len(parts) < len(best[1]):
            best = (member, parts)
    return best


def _peek_manifest(archive, nested=False):
    """Return (manifest, unpacked size) of a pack archive, or of the one .rafpack in a zip."""
    members = archive.infolist()
    found = _find_manifest(members)
    if found is not None:
        manifest = json.loads(archive.read(found[0]).decode("utf-8"))
        _validate_manifest(manifest)
        return manifest, sum(member.file_size for member in members)
    inner = [m for m in members if m.filename.lower().endswith(PACK_EXTENSION)]
    if len(inner) != 1 or nested:
        raise ValueError("not a RAF Scatter biome pack")
    with archive.open(inner[0]) as handle, zipfile.ZipFile(handle) as inner_archive:
        return _peek_manifest(inner_archive, nested=True)


def format_size(size):
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def installed_pack_version(name):
    """Return the version of the installed pack with this name, '' if unknown, None if absent."""
    root = os.path.join(biomes_utils.get_packs_dir(), biomes_utils.sanitize_biome_name(name))
    if not os.path.isdir(root):
        return None
    try:
        return str(_read_manifest(root).get("version", ""))
    except ValueError:
        return ""


def read_pack_summary(filepath):
    """Return what the installer shows about a pack file, or None when no file is chosen."""
    if not filepath or not os.path.isfile(filepath):
        return None
    stat = os.stat(filepath)
    key = (os.path.normcase(filepath), stat.st_mtime, stat.st_size)
    if key not in _summary_cache:
        try:
            with zipfile.ZipFile(filepath) as archive:
                manifest, size = _peek_manifest(archive)
            biomes = manifest.get("biomes")
            summary = {
                "name": manifest["name"],
                "version": str(manifest.get("version", "")),
                "author": str(manifest.get("author", "")),
                "biomes": len(biomes) if isinstance(biomes, list) else 0,
                "size": size,
            }
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            summary = {"error": str(error)}
        if len(_summary_cache) > _SUMMARY_CACHE_SIZE:
            _summary_cache.clear()
        _summary_cache[key] = summary
    return _summary_cache[key]


def _install_members(archive, members, prefix, staging):
    """Extract the pack files below prefix into staging; return how many files were skipped."""
    skipped = 0
    for member in members:
        if member.is_dir():
            continue
        parts = _member_parts(member.filename)
        relative = parts[len(prefix):] if parts and parts[:len(prefix)] == prefix else None
        if not relative or os.path.splitext(relative[-1])[1].lower() not in _ALLOWED_EXTENSIONS:
            skipped += 1
            continue
        target = os.path.join(staging, *relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as handle:
            shutil.copyfileobj(source, handle)
    return skipped


def _install_nested(archive, member, add_asset_library):
    """Install the single .rafpack stored inside a downloaded zip."""
    work = tempfile.mkdtemp(prefix="raf_pack_")
    try:
        inner = os.path.join(work, "pack" + PACK_EXTENSION)
        with archive.open(member) as source, open(inner, "wb") as handle:
            shutil.copyfileobj(source, handle)
        return install_pack(inner, add_asset_library, nested=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_pack(filepath, add_asset_library, nested=False):
    """Install a .rafpack, or a .zip holding one; return (manifest, skipped file count)."""
    if not zipfile.is_zipfile(filepath):
        raise ValueError("not a RAF Scatter biome pack")
    with zipfile.ZipFile(filepath) as archive:
        members = archive.infolist()
        found = _find_manifest(members)
        if found is None:
            inner = [m for m in members if m.filename.lower().endswith(PACK_EXTENSION)]
            if len(inner) == 1 and not nested:
                return _install_nested(archive, inner[0], add_asset_library)
            raise ValueError(f"no {PACK_MANIFEST} found — not a RAF Scatter biome pack")
        manifest_member, manifest_parts = found
        manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
        _validate_manifest(manifest)
        packs_dir = biomes_utils.get_packs_dir()
        if not packs_dir:
            raise ValueError("Blender's user scripts folder is not available")
        needed = sum(member.file_size for member in members)
        if needed > shutil.disk_usage(packs_dir).free:
            raise ValueError("not enough free disk space")
        pack_id = biomes_utils.sanitize_biome_name(manifest["name"])
        target = os.path.join(packs_dir, pack_id)
        staging = os.path.join(packs_dir, _INSTALL_PREFIX + pack_id)
        shutil.rmtree(staging, ignore_errors=True)
        try:
            skipped = _install_members(archive, members, manifest_parts[:-1], staging)
            if os.path.isdir(target):
                shutil.rmtree(target)
            os.replace(staging, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    if add_asset_library:
        add_pack_asset_library(target, manifest["name"])
    return manifest, skipped


def uninstall_pack(pack_id):
    """Remove an installed pack folder and its asset library entry."""
    packs_dir = biomes_utils.get_packs_dir()
    root = os.path.normpath(os.path.join(packs_dir, pack_id))
    inside = bool(packs_dir) and bool(pack_id) and os.path.dirname(root) == packs_dir
    if not inside or not os.path.isdir(root):
        raise ValueError("pack not found")
    remove_pack_asset_library(root)
    shutil.rmtree(root)


#----EXPORT----
def _iter_asset_entries(data):
    """Yield every instance asset reference of biome data, members included."""
    pending = []
    for system in data["systems"]:
        instances = system.get("instances") or {}
        pending += [instances.get("object"), instances.get("collection")]
    while pending:
        entry = pending.pop()
        if not isinstance(entry, dict):
            continue
        yield entry
        pending += entry.get("members") or []


def _plan_asset(entry, scene, session_path, session_ids):
    """Return the (file, name) an asset entry is exported from, or None when it is unavailable."""
    name = entry.get("name")
    if not isinstance(name, str) or not name or "members" in entry:
        return None
    source = entry.get("source")
    if isinstance(source, str):
        filepath, _separator, asset_name = source.rpartition("::")
        return (filepath, asset_name) if asset_name and os.path.isfile(filepath) else None
    idb = biomes_utils.find_scene_object(scene, name)
    idb = idb or biomes_utils.find_scene_collection(scene, name)
    if idb is None:
        return None
    session_ids.add(idb)
    return (session_path, idb.name)


def _rewrite_asset_entry(entry, packed_name, missing):
    """Point an asset entry at the pack's assets file and drop the author's own paths."""
    entry.pop("source", None)
    if "members" in entry:
        return
    if packed_name is None:
        missing.append(str(entry.get("name", "?")))
        return
    entry["name"] = packed_name
    entry["pack_source"] = f"{PACK_ASSETS_FILE}::{packed_name}"


def _run_worker(requests, output, work):
    """Write the requested assets into output with a background Blender; return its result."""
    binary = bpy.app.binary_path
    if not binary or not os.path.isfile(binary):
        raise RuntimeError("the Blender executable was not found")
    job_path = os.path.join(work, "job.json")
    result_path = os.path.join(work, "result.json")
    job = {
        "output": output,
        "result": result_path,
        "requests": [
            {"id": request_id, "filepath": filepath, "name": name}
            for (filepath, name), request_id in requests.items()
        ],
    }
    with open(job_path, "w", encoding="utf-8") as handle:
        json.dump(job, handle)
    command = [
        binary, "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", _WORKER_SCRIPT, "--", job_path,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_WORKER_TIMEOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("writing the pack assets timed out") from error
    if completed.returncode != 0 or not os.path.isfile(result_path):
        lines = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise RuntimeError("writing the pack assets failed" + (f": {lines[-1]}" if lines else ""))
    with open(result_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _unique_filename(filename, used):
    stem, extension = os.path.splitext(filename)
    candidate, number = filename, 1
    while candidate.lower() in used:
        candidate = f"{stem}_{number}{extension}"
        number += 1
    used.add(candidate.lower())
    return candidate


def _copy_texture(refs, pack_dir, copied, used):
    """Copy an effector image into the pack; return its pack-relative path, or None."""
    source = refs.pop("image_filepath", None)
    image = bpy.data.images.get(refs["image"])
    if isinstance(source, str) and os.path.isfile(source):
        key = os.path.normcase(os.path.normpath(source))
        filename, data = os.path.basename(source), None
    elif image is not None and image.packed_file is not None:
        key = "packed:" + image.name
        extension = os.path.splitext(image.filepath)[1] or ".png"
        filename = biomes_utils.sanitize_biome_name(os.path.splitext(image.name)[0]) + extension
        data = image.packed_file.data
    else:
        return None
    if key in copied:
        return copied[key]
    relative = f"{PACK_TEXTURE_DIR}/{_unique_filename(filename, used)}"
    target = os.path.join(pack_dir, *relative.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if data is None:
        shutil.copyfile(source, target)
    else:
        with open(target, "wb") as handle:
            handle.write(data)
    copied[key] = relative
    return relative


def _pack_effector_images(data, pack_dir, copied, used, missing):
    for system in data["systems"]:
        for effector in system.get("effectors", []):
            refs = effector.get("refs") or {}
            if "image" not in refs:
                continue
            relative = _copy_texture(refs, pack_dir, copied, used)
            if relative is None:
                missing.append(refs["image"])
            else:
                refs["pack_image"] = relative


def _write_biome(pack_dir, name, data):
    folder = os.path.join(pack_dir, biomes_utils.PACK_BIOME_SUBDIR)
    os.makedirs(folder, exist_ok=True)
    data["name"] = name
    path = os.path.join(folder, name + biomes_utils.BIOME_EXTENSION)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    thumbnail = biomes_utils.find_thumbnail(name)
    if thumbnail is not None:
        extension = os.path.splitext(thumbnail)[1].lower()
        shutil.copyfile(thumbnail, os.path.join(folder, name + extension))


def _zip_folder(folder, filepath):
    """Zip a folder into filepath, replacing the file only once the archive is complete."""
    partial = filepath + ".part"
    with zipfile.ZipFile(partial, "w") as archive:
        for root, _dirs, files in os.walk(folder):
            for filename in files:
                path = os.path.join(root, filename)
                text = os.path.splitext(filename)[1].lower() in _TEXT_EXTENSIONS
                archive.write(
                    path, os.path.relpath(path, folder).replace(os.sep, "/"),
                    compress_type=zipfile.ZIP_DEFLATED if text else zipfile.ZIP_STORED,
                )
    os.replace(partial, filepath)


def export_pack(filepath, name, author, version, biome_names):
    """Write saved biomes, their instance assets and mask images to a .rafpack; return a summary."""
    biomes = [(biome_name, biomes_utils.read_biome(biome_name)) for biome_name in biome_names]
    scene = bpy.context.scene
    work = tempfile.mkdtemp(prefix="raf_pack_")
    try:
        pack_dir = os.path.join(work, "pack")
        os.makedirs(pack_dir)
        session_path = os.path.join(work, "session.blend")
        requests, session_ids, planned = {}, set(), []
        for _biome_name, data in biomes:
            for entry in _iter_asset_entries(data):
                key = _plan_asset(entry, scene, session_path, session_ids)
                if key is not None:
                    requests.setdefault(key, f"asset_{len(requests)}")
                planned.append((entry, key))
        if session_ids:
            bpy.data.libraries.write(session_path, session_ids, path_remap='ABSOLUTE')
        result = {"names": {}, "missing_images": []}
        if requests:
            output = os.path.join(pack_dir, *PACK_ASSETS_FILE.split("/"))
            result = _run_worker(requests, output, work)
        missing_assets, missing_images, copied, used = [], list(result["missing_images"]), {}, set()
        for entry, key in planned:
            packed_name = result["names"].get(requests[key]) if key is not None else None
            _rewrite_asset_entry(entry, packed_name, missing_assets)
        for biome_name, data in biomes:
            _pack_effector_images(data, pack_dir, copied, used, missing_images)
            _write_biome(pack_dir, biome_name, data)
        manifest = {
            "format": PACK_FORMAT, "kind": PACK_KIND, "name": name, "author": author,
            "version": version, "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "blender_version": bpy.app.version_string, "biomes": [n for n, _data in biomes],
        }
        with open(os.path.join(pack_dir, PACK_MANIFEST), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        _zip_folder(pack_dir, filepath)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {
        "biomes": len(biomes),
        "assets": len(result["names"]),
        "missing_assets": sorted(set(missing_assets)),
        "missing_images": sorted(set(missing_images)),
    }
