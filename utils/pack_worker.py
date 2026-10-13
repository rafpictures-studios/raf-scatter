"""Background Blender job that writes the instance assets of a biome pack into one .blend."""
import json
import os
import sys

import bpy


_PACKABLE_SOURCES = {'FILE', 'SEQUENCE', 'TILED'}
_LOCAL_ID_TYPES = (
    "objects", "collections", "meshes", "curves", "hair_curves", "pointclouds", "volumes",
    "materials", "node_groups", "images", "textures", "lights", "grease_pencils", "fonts",
)


#----ASSET LOADING----
def _append_requests(requests):
    """Append every requested object or collection; return request id -> datablock."""
    by_file = {}
    for request in requests:
        by_file.setdefault(request["filepath"], []).append(request)
    loaded = {}
    for filepath, file_requests in by_file.items():
        names = list(dict.fromkeys(request["name"] for request in file_requests))
        try:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                objects = [name for name in names if name in data_from.objects]
                collections = [
                    name for name in names if name not in objects and name in data_from.collections
                ]
                # copies: Blender replaces the assigned list items with the loaded IDs
                data_to.objects = list(objects)
                data_to.collections = list(collections)
        except OSError:
            continue
        found = dict(zip(objects, data_to.objects))
        found.update(zip(collections, data_to.collections))
        for request in file_requests:
            if found.get(request["name"]) is not None:
                loaded[request["id"]] = found[request["name"]]
    return loaded


def _make_everything_local():
    """Localize data the source files linked from further libraries."""
    for id_type in _LOCAL_ID_TYPES:
        for idb in list(getattr(bpy.data, id_type, ())):
            if idb.library is not None:
                idb.make_local()


def _pack_images():
    """Pack every external image into the file; return the names that could not be packed."""
    missing = []
    for image in bpy.data.images:
        if image.packed_file is not None or image.source not in _PACKABLE_SOURCES:
            continue
        try:
            image.pack()
        except RuntimeError:
            missing.append(image.name)
            # no absolute path from the author's machine may travel with the pack
            image.filepath = "//" + os.path.basename(bpy.path.abspath(image.filepath))
    return missing


#----JOB----
def run(job_path):
    with open(job_path, "r", encoding="utf-8") as handle:
        job = json.load(handle)
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    loaded = _append_requests(job["requests"])
    _make_everything_local()
    missing_images = _pack_images()
    for idb in loaded.values():
        if idb.asset_data is None:
            idb.asset_mark()
    if loaded:
        os.makedirs(os.path.dirname(job["output"]), exist_ok=True)
        bpy.data.libraries.write(
            job["output"], set(loaded.values()), path_remap='NONE', fake_user=True, compress=True,
        )
    result = {
        "names": {request_id: idb.name for request_id, idb in loaded.items()},
        "missing_images": missing_images,
    }
    with open(job["result"], "w", encoding="utf-8") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--") + 1])
