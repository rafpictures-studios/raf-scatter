"""Addon preferences for RAF Scatter."""
import sys
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences

from .utils import icons as icon_utils
from .utils import updates as updates_utils


BIOME_GROUP_LOCAL = 'LOCAL'
BIOME_GROUP_IMPORTED = 'IMPORTED'
_BIOME_GROUP_ITEMS = (
    (BIOME_GROUP_LOCAL, "My Biomes", "Biomes saved on this computer", 'HOME', 0),
    (BIOME_GROUP_IMPORTED, "Imported", "Biomes from installed packs (read-only)", 'PACKAGE', 1),
)
_ALL = "ALL"
_PREVIEW_SCALE = 5.0
_PLACEHOLDER_HOST = "example.com"
_LINKS = (
    ("Website", "https://raf-scatter-docs.vercel.app/", 'WORLD'),
    ("Instagram", "https://www.instagram.com/rizqyalfajri/", 'IMAGE_DATA'),
    ("YouTube", "https://www.youtube.com/@rafpictures_studios", 'FILE_MOVIE'),
)
_items_cache = []


#----LIBRARY ITEMS----
def _library_items(self, context):
    """Build the dropdown from registered asset libraries."""
    global _items_cache
    items = [(_ALL, "All Libraries", "Open the Asset Browser on every registered library")]
    seen = {_ALL}
    for lib in bpy.context.preferences.filepaths.asset_libraries:
        if lib.name and lib.name not in seen:
            seen.add(lib.name)
            items.append((lib.name, lib.name, lib.path))
    _items_cache = items
    return _items_cache


def _get_library(self):
    """Return the current dropdown index."""
    items = _library_items(self, None)
    for index, item in enumerate(items):
        if item[0] == self.default_library_name:
            return index
    return 0


def _set_library(self, value):
    """Store the selected library name from the dropdown index."""
    items = _library_items(self, None)
    if 0 <= value < len(items):
        self.default_library_name = items[value][0]


#----BIOME GROUPS----
def get_addon_prefs(context=None):
    addon = (context or bpy.context).preferences.addons.get(__package__)
    return addon.preferences if addon else None


def is_biome_in_group(item, group):
    return bool(item.pack_id) == (group == BIOME_GROUP_IMPORTED)


def grouped_biome_indices(wm, group):
    """Return the indices of the listed biomes that belong to a group."""
    return [index for index, item in enumerate(wm.scatter_biomes) if is_biome_in_group(item, group)]


def sync_biome_selection(context=None, group=None):
    """Select the first biome of the shown group when the active one is in another group."""
    context = context or bpy.context
    prefs = get_addon_prefs(context)
    if prefs is None:
        return
    if group is not None:
        prefs.biome_group = group
    wm = context.window_manager
    indices = grouped_biome_indices(wm, prefs.biome_group)
    if indices and wm.scatter_active_biome_index not in indices:
        wm.scatter_active_biome_index = indices[0]
    picked = [i for i in indices if wm.scatter_biomes[i].valid]
    names = {wm.scatter_biomes[i].name for i in picked}
    if picked and wm.scatter_biome_pick not in names:
        wm.scatter_biome_pick = wm.scatter_biomes[picked[0]].name


def _on_biome_group_update(self, context):
    sync_biome_selection(context)


#----DRAW HELPERS----
def _is_live_url(url):
    return bool(url) and _PLACEHOLDER_HOST not in url


def _draw_hint(layout, text):
    row = layout.row()
    row.active = False
    row.label(text=text)


def _draw_biome_details(layout, item):
    """Draw the preview, description and file info of the selected biome."""
    box = layout.box()
    split = box.split(factor=0.3)
    preview = split.column(align=True)
    thumbnail = icon_utils.get_biome_icon_id(item.name)
    preview.template_icon(
        icon_value=thumbnail or icon_utils.get_biome_logo_value(),
        scale=_PREVIEW_SCALE,
    )
    if not item.pack_id:
        buttons = preview.row(align=True)
        op = buttons.operator("scatter.set_biome_preview", text="Set Preview", icon='IMAGE_DATA')
        op.biome_name = item.name
        op = buttons.operator(
            "scatter.capture_biome_preview", text="Capture", icon='RESTRICT_RENDER_OFF',
        )
        op.biome_name = item.name
    info = split.column()
    info.label(text=item.label, icon='ERROR' if not item.valid else 'NONE')
    if not item.valid:
        hint = "reinstall the pack" if item.pack_id else "rename or delete it"
        info.label(text=f"File cannot be read — {hint}")
        return
    detail = info.column(align=True)
    detail.active = False
    if item.pack_id:
        detail.label(text=f"Pack: {item.pack_name} (read-only)", icon='PACKAGE')
    systems = item.manual_count + item.procedural_count
    detail.label(text=f"{systems} system(s): {item.procedural_count} procedural, "
                      f"{item.manual_count} paint")
    detail.label(text=f"Created: {item.created.replace('T', ' ')}")
    if item.modified and item.modified != item.created:
        detail.label(text=f"Modified: {item.modified.replace('T', ' ')}")
    detail.label(text=f"Location: {item.file_path}")


def _draw_installed_packs(layout, wm):
    header, body = layout.panel("RAF_SCATTER_prefs_packs", default_closed=False)
    header.label(text="Installed Packs", icon='PACKAGE')
    if body is None:
        return
    box = body.box()
    if len(wm.scatter_packs) == 0:
        _draw_hint(box, "No packs installed yet — use Install Pack… above")
        return
    col = box.column(align=True)
    for pack in wm.scatter_packs:
        row = col.row()
        parts = [pack.title]
        if pack.version:
            parts.append(f"v{pack.version}")
        if pack.author:
            parts.append(pack.author)
        parts.append(f"{pack.biome_count} biome(s)")
        row.label(text="  ·  ".join(parts), icon='PACKAGE' if pack.valid else 'ERROR')
        buttons = row.row(align=True)
        buttons.alignment = 'RIGHT'
        op = buttons.operator("scatter.open_pack_folder", text="Open Folder", icon='FILE_FOLDER')
        op.pack_id = pack.name
        op = buttons.operator("scatter.uninstall_pack", text="Uninstall", icon='TRASH')
        op.pack_id = pack.name


def _update_status_text():
    state = updates_utils.state
    status = state["status"]
    if status == updates_utils.STATUS_CHECKING:
        return "Checking…"
    installed = updates_utils.installed_version_text()
    if status == updates_utils.STATUS_ERROR:
        return "Could not reach the website. Check your internet connection and try again."
    if status == updates_utils.STATUS_IDLE:
        return f"You have RAF Scatter {installed}."
    checked = time.strftime("%d %b %Y %H:%M", time.localtime(state["checked"]))
    if status == updates_utils.STATUS_AVAILABLE:
        return f"RAF Scatter {state['version']} is available (you have {installed}). Checked {checked}."
    return f"RAF Scatter {installed} is the latest version. Checked {checked}."


def _draw_update_notice(layout):
    state = updates_utils.state
    if state["status"] != updates_utils.STATUS_AVAILABLE:
        return
    box = layout.box()
    row = box.row()
    row.label(text=f"RAF Scatter {state['version']} is available", icon='INFO')
    row.operator("wm.url_open", text="Download", icon='URL').url = state["url"]
    if state["message"]:
        _draw_hint(box, state["message"])
    _draw_hint(box, f"You have {updates_utils.installed_version_text()}.")


#----PREFERENCES PANEL----
class SCATTER_AP_preferences(AddonPreferences):
    bl_idname = __package__

    default_library_name: StringProperty(default=_ALL, options={'HIDDEN'})
    pack_author: StringProperty(name="Pack Author", options={'HIDDEN'})
    biome_group: EnumProperty(
        name="Biome Group", items=_BIOME_GROUP_ITEMS, update=_on_biome_group_update,
    )
    check_updates: BoolProperty(
        name="Check for Updates",
        description="Once a day, ask the RAF Pictures website whether a newer RAF Scatter is available",
        default=True,
    )
    default_library: EnumProperty(
        name="Default Library",
        description="Library the Scatter Library (Asset Browser) opens on",
        items=_library_items,
        get=_get_library,
        set=_set_library,
    )

    def draw(self, context):
        layout = self.layout
        _draw_update_notice(layout)
        self._draw_scatter_library(layout)
        self._draw_biome_library(layout, context)
        self._draw_updates(layout)
        self._draw_links(layout)

    def _draw_scatter_library(self, layout):
        header, body = layout.panel("RAF_SCATTER_prefs_library", default_closed=False)
        header.label(text="Scatter Library", icon='FILEBROWSER')
        if body is None:
            return
        col = body.column()
        col.use_property_split = True
        col.prop(self, "default_library")
        if not bpy.context.preferences.filepaths.asset_libraries:
            _draw_hint(body, "No custom asset libraries registered yet.")
        _draw_hint(body, "Register libraries in Preferences > File Paths > Asset Libraries.")

    def _draw_biome_library(self, layout, context):
        header, body = layout.panel("RAF_SCATTER_prefs_biomes", default_closed=False)
        header.label(text="Biome Library", icon_value=icon_utils.get_biome_logo_value())
        if body is None:
            return
        wm = context.window_manager
        imported = self.biome_group == BIOME_GROUP_IMPORTED
        indices = grouped_biome_indices(wm, self.biome_group)
        active = None
        if wm.scatter_active_biome_index in indices:
            active = wm.scatter_biomes[wm.scatter_active_biome_index]
        tools = body.row(align=True)
        tools.operator("scatter.install_pack", text="Install Pack…", icon='PACKAGE')
        tools.operator("scatter.export_pack", text="Export Pack…", icon='EXPORT')
        body.row(align=True).prop(self, "biome_group", text="")
        row = body.row()
        row.template_list(
            "SCATTER_UL_biomes", "", wm, "scatter_biomes", wm, "scatter_active_biome_index",
            rows=6,
        )
        side = row.column(align=True)
        if imported:
            folder = side.row(align=True)
            folder.enabled = active is not None
            op = folder.operator("scatter.open_pack_folder", text="", icon='FILE_FOLDER')
            op.pack_id = active.pack_id if active else ""
        else:
            actions = side.column(align=True)
            actions.enabled = active is not None
            biome_name = active.name if active else ""
            op = actions.operator("scatter.rename_biome", text="", icon='GREASEPENCIL')
            op.biome_name = biome_name
            actions.operator("scatter.delete_biome", text="", icon='REMOVE').biome_name = biome_name
            side.separator()
            side.operator("scatter.open_biome_folder", text="", icon='FILE_FOLDER')
        if not indices and imported:
            _draw_hint(body, "No packs installed yet — use Install Pack… above")
        elif not indices:
            _draw_hint(body, "No biomes saved yet — save one from the Biomes popup in the N-panel")
        elif active is not None:
            _draw_biome_details(body, active)
        _draw_installed_packs(body, wm)

    def _draw_updates(self, layout):
        header, body = layout.panel("RAF_SCATTER_prefs_updates", default_closed=True)
        header.label(text="Updates", icon='FILE_REFRESH')
        if body is None:
            return
        row = body.row()
        row.prop(self, "check_updates")
        row.operator("scatter.check_updates", icon='FILE_REFRESH')
        if not updates_utils.online_allowed():
            _draw_hint(body, "Online access is off: turn on Allow Online Access in Preferences > System.")
            return
        _draw_hint(body, _update_status_text())

    def _draw_links(self, layout):
        header, body = layout.panel("RAF_SCATTER_prefs_links", default_closed=True)
        header.label(text="Links", icon='URL')
        if body is None:
            return
        row = body.row(align=True)
        row.scale_y = 1.3
        for text, url, icon in _LINKS:
            cell = row.row(align=True)
            cell.enabled = _is_live_url(url)
            label = text if cell.enabled else f"{text} (soon)"
            cell.operator("wm.url_open", text=label, icon=icon).url = url
        info = sys.modules[__package__].bl_info
        version = ".".join(str(number) for number in info.get("version", ()))
        _draw_hint(body, f"{info.get('name', 'RAF Scatter')} {version}  ·  {info.get('author', '')}")


#----REGISTRATION----
classes = (
    SCATTER_AP_preferences,
)


def register():
    """Register preference classes."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister preference classes."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
