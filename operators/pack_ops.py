"""Operators for installing, exporting and uninstalling biome packs."""
import os
import zipfile

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from .biome_ops import refresh_biome_library
from ..preferences import BIOME_GROUP_IMPORTED, sync_biome_selection
from ..utils import biomes as biomes_utils
from ..utils import packs as packs_utils


_ADDON_ID = __package__.split(".")[0]
_EXPORT_DIALOG_WIDTH = 360
_INSTALL_FILTER = f"*{packs_utils.PACK_EXTENSION};*.zip"


#----HELPERS----
def _get_prefs(context):
    addon = context.preferences.addons.get(_ADDON_ID)
    return addon.preferences if addon else None


def _exportable_biomes(context):
    """Return the listed saved biomes that can go into a pack (pack biomes excluded)."""
    biomes = context.window_manager.scatter_biomes
    return [item for item in biomes if item.valid and not item.pack_id]


def _pack_title(context, pack_id):
    for pack in context.window_manager.scatter_packs:
        if pack.name == pack_id:
            return pack.title
    return pack_id


def _version_author(version, author):
    parts = [f"v{version}" if version else "", f"by {author}" if author else ""]
    return "  ·  ".join(part for part in parts if part)


def _draw_dim_lines(layout, lines):
    col = layout.column(align=True)
    col.active = False
    for line in lines:
        col.label(text=line)


def _draw_install_summary(layout, filepath):
    """Draw what the selected file holds, as read from its pack.json."""
    summary = packs_utils.read_pack_summary(filepath)
    if summary is None:
        _draw_dim_lines(layout, ("Select a .rafpack file,", "or a .zip that holds one"))
        return
    if "error" in summary:
        layout.label(text="Not a RAF Scatter biome pack", icon='ERROR')
        return
    layout.label(text=summary["name"], icon='PACKAGE')
    meta = _version_author(summary["version"], summary["author"])
    lines = [meta] if meta else []
    lines.append(f"{summary['biomes']} biome(s)  ·  {packs_utils.format_size(summary['size'])}")
    _draw_dim_lines(layout, lines)
    installed = packs_utils.installed_pack_version(summary["name"])
    if installed is not None:
        current = f" v{installed}" if installed else ""
        layout.label(text=f"Installed{current} will be replaced", icon='INFO')


#----OPERATORS----
class SCATTER_OT_install_pack(Operator):
    bl_idname = "scatter.install_pack"
    bl_label = "Install Pack"
    bl_description = "Install a biome pack (.rafpack) so its biomes can be loaded"
    bl_options = {'REGISTER'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default=_INSTALL_FILTER, options={'HIDDEN'})
    add_asset_library: BoolProperty(
        name="Add pack assets to Asset Browser",
        description="Register the pack's assets folder as an asset library in the Preferences",
        default=True,
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        header, body = self.layout.panel("SCATTER_install_pack", default_closed=False)
        header.label(text="RAF Biome Installer", icon='PACKAGE')
        if body is None:
            return
        _draw_install_summary(body, bpy.path.abspath(self.filepath))
        body.separator()
        body.prop(self, "add_asset_library")
        _draw_dim_lines(body, ("Lets you drag the pack's assets", "from the Asset Browser"))

    def execute(self, context):
        try:
            manifest, skipped = packs_utils.install_pack(
                bpy.path.abspath(self.filepath), self.add_asset_library,
            )
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            self.report({'ERROR'}, f"Could not install the pack: {error}")
            return {'CANCELLED'}
        wm = context.window_manager
        pack_id = biomes_utils.sanitize_biome_name(manifest["name"])
        first = next(iter(biomes_utils.list_pack_biomes(pack_id)), (None, None))[0]
        refresh_biome_library(context, select=first)
        sync_biome_selection(context, BIOME_GROUP_IMPORTED)
        count = sum(1 for item in wm.scatter_biomes if item.pack_id == pack_id)
        version = f" v{manifest['version']}" if manifest.get("version") else ""
        message = f"Installed pack \"{manifest['name']}\"{version}: {count} biome(s)"
        if skipped:
            message += f"; {skipped} unsupported file(s) skipped"
        self.report({'INFO'}, message)
        return {'FINISHED'}


class SCATTER_OT_export_pack(Operator):
    bl_idname = "scatter.export_pack"
    bl_label = "Export Biome Pack"
    bl_description = "Bundle saved biomes with their instance assets into one file to share"
    bl_options = {'REGISTER'}

    pack_name: StringProperty(name="Name", default="Biome Pack")
    author: StringProperty(name="Author")
    version: StringProperty(name="Version", default="1.0.0")

    @classmethod
    def poll(cls, context):
        return bool(_exportable_biomes(context))

    def invoke(self, context, event):
        prefs = _get_prefs(context)
        if prefs is not None and not self.author:
            self.author = prefs.pack_author
        biomes = _exportable_biomes(context)
        if not any(item.pack_include for item in biomes):
            wm = context.window_manager
            if 0 <= wm.scatter_active_biome_index < len(wm.scatter_biomes):
                active = wm.scatter_biomes[wm.scatter_active_biome_index]
                if active in biomes:
                    active.pack_include = True
        return context.window_manager.invoke_props_dialog(
            self, width=_EXPORT_DIALOG_WIDTH, title="Export Biome Pack", confirm_text="Export…",
        )

    def draw(self, context):
        layout = self.layout
        fields = layout.column()
        fields.use_property_split = True
        fields.prop(self, "pack_name")
        fields.prop(self, "author")
        fields.prop(self, "version")
        layout.label(text="Biomes")
        biomes = layout.column(align=True)
        for item in _exportable_biomes(context):
            biomes.prop(item, "pack_include", text=item.label)
        hint = layout.row()
        hint.active = False
        hint.label(text="Only include assets you have the right to share", icon='INFO')

    def execute(self, context):
        names = [item.name for item in _exportable_biomes(context) if item.pack_include]
        if not names:
            self.report({'WARNING'}, "Tick at least one biome to export")
            return {'CANCELLED'}
        if not biomes_utils.sanitize_biome_name(self.pack_name):
            self.report({'WARNING'}, "Enter a pack name")
            return {'CANCELLED'}
        prefs = _get_prefs(context)
        if prefs is not None:
            prefs.pack_author = self.author
        bpy.ops.scatter.export_pack_file(
            'INVOKE_DEFAULT', pack_name=self.pack_name, author=self.author,
            version=self.version, biome_names="\n".join(names),
        )
        return {'FINISHED'}


class SCATTER_OT_export_pack_file(Operator):
    bl_idname = "scatter.export_pack_file"
    bl_label = "Export Pack"
    bl_description = "Choose where to save the biome pack"
    bl_options = {'REGISTER', 'INTERNAL'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default=f"*{packs_utils.PACK_EXTENSION}", options={'HIDDEN'})
    check_existing: BoolProperty(default=True, options={'HIDDEN'})
    pack_name: StringProperty(options={'HIDDEN'})
    author: StringProperty(options={'HIDDEN'})
    version: StringProperty(options={'HIDDEN'})
    biome_names: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        filename = biomes_utils.sanitize_biome_name(self.pack_name) + packs_utils.PACK_EXTENSION
        self.filepath = filename
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        header, body = self.layout.panel("SCATTER_export_pack_file", default_closed=False)
        header.label(text="RAF Biome Pack Export", icon='EXPORT')
        if body is None:
            return
        body.label(text=self.pack_name, icon='PACKAGE')
        names = [name for name in self.biome_names.split("\n") if name]
        meta = _version_author(self.version, self.author)
        lines = [meta] if meta else []
        lines.append(f"{len(names)} biome(s): {', '.join(names)}")
        _draw_dim_lines(body, lines)

    def check(self, context):
        filepath = bpy.path.ensure_ext(self.filepath, packs_utils.PACK_EXTENSION)
        if filepath == self.filepath:
            return False
        self.filepath = filepath
        return True

    def execute(self, context):
        filepath = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), packs_utils.PACK_EXTENSION)
        names = [name for name in self.biome_names.split("\n") if name]
        window = context.window
        if window is not None:
            window.cursor_set('WAIT')
        try:
            summary = packs_utils.export_pack(
                filepath, self.pack_name, self.author, self.version, names,
            )
        except (OSError, RuntimeError, ValueError) as error:
            self.report({'ERROR'}, f"Could not export the pack: {error}")
            return {'CANCELLED'}
        finally:
            if window is not None:
                window.cursor_set('DEFAULT')
        message = (
            f"Exported \"{self.pack_name}\": {summary['biomes']} biome(s), "
            f"{summary['assets']} asset(s)"
        )
        missing = summary["missing_assets"] + summary["missing_images"]
        if missing:
            message += f"; not included: {', '.join(missing)}"
        self.report({'WARNING'} if missing else {'INFO'}, message)
        return {'FINISHED'}


class SCATTER_OT_uninstall_pack(Operator):
    bl_idname = "scatter.uninstall_pack"
    bl_label = "Uninstall Pack"
    bl_description = "Remove the pack, its biomes and its assets from disk"
    bl_options = {'REGISTER'}

    pack_id: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        title = _pack_title(context, self.pack_id)
        return context.window_manager.invoke_confirm(
            self, event, title="Uninstall Pack",
            message=f"Remove \"{title}\" with its biomes and assets from disk?",
            confirm_text="Uninstall",
        )

    def execute(self, context):
        title = _pack_title(context, self.pack_id)
        try:
            packs_utils.uninstall_pack(self.pack_id)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Could not uninstall the pack: {error}")
            return {'CANCELLED'}
        refresh_biome_library(context)
        sync_biome_selection(context)
        self.report({'INFO'}, f"Uninstalled pack \"{title}\"")
        return {'FINISHED'}


class SCATTER_OT_open_pack_folder(Operator):
    bl_idname = "scatter.open_pack_folder"
    bl_label = "Open Pack Folder"
    bl_description = "Open the folder of the installed pack in the file manager"
    bl_options = {'REGISTER'}

    pack_id: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        root = os.path.join(biomes_utils.get_packs_dir(), self.pack_id)
        if not self.pack_id or not os.path.isdir(root):
            self.report({'WARNING'}, "Pack folder not found")
            return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=root)
        return {'FINISHED'}


classes = (
    SCATTER_OT_install_pack,
    SCATTER_OT_export_pack,
    SCATTER_OT_export_pack_file,
    SCATTER_OT_uninstall_pack,
    SCATTER_OT_open_pack_folder,
)
