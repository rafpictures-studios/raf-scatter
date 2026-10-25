"""Ambient occlusion bake of a target ground into a color attribute (Cycles)."""
import bpy
import numpy as np


AO_ATTRIBUTE_NAME = "colorAO_id"
_PASS_ATTRIBUTE_NAME = "colorAO_id_pass"
BAKE_PASSES = 16
_PASS_SAMPLES = 4
_ERROR_PREFIX = "Error: "


def has_baked_ao(ground):
    """True when the ground mesh carries the baked AO color attribute."""
    return (
        ground is not None
        and ground.type == 'MESH'
        and AO_ATTRIBUTE_NAME in ground.data.color_attributes
    )


def _scatter_curves(scene):
    """Curve objects of every scatter system, so the scatter does not occlude its own ground."""
    return [
        system.curve_obj
        for ground in scene.scatter_grounds for system in ground.scatter_systems
        if system.curve_obj is not None
    ]


class AOBake:
    """An AO bake split into passes: start(), step() until done, then finish() or cancel()."""

    def __init__(self, context, ground):
        self.scene = context.scene
        self.ground = ground
        self.done = 0
        self._sum = None
        self._saved = None

    @property
    def progress(self):
        return self.done / BAKE_PASSES

    def start(self, context):
        """Prepare the scene for the passes; return an error text or None."""
        ground = self.ground
        if ground is None or ground.type != 'MESH':
            return "The Target Ground is not a mesh"
        if context.preferences.addons.get("cycles") is None:
            return "Baking needs the Cycles render engine (enable it in the preferences)"
        scene = self.scene
        colors = ground.data.color_attributes
        active = colors.active_color
        hidden = [obj for obj in _scatter_curves(scene) if not obj.hide_render]
        self._saved = {
            "active_color": active.name if active is not None else None,
            "engine": scene.render.engine,
            "target": scene.render.bake.target,
            "hidden": hidden,
        }
        work = colors.get(_PASS_ATTRIBUTE_NAME)
        if work is None:
            work = colors.new(_PASS_ATTRIBUTE_NAME, 'FLOAT_COLOR', 'POINT')
        colors.active_color = work
        for obj in hidden:
            obj.hide_render = True
        scene.render.engine = 'CYCLES'
        self._saved["samples"] = scene.cycles.samples
        self._saved["seed"] = scene.cycles.seed
        scene.cycles.samples = _PASS_SAMPLES
        self._sum = np.zeros(len(ground.data.vertices), dtype=np.float64)
        return None

    def step(self, context):
        """Bake one pass; return an error text or None."""
        self.scene.cycles.seed = self.done
        ground = self.ground
        try:
            with context.temp_override(
                active_object=ground, object=ground,
                selected_objects=[ground], selected_editable_objects=[ground],
            ):
                bpy.ops.object.bake(
                    type='AO', target='VERTEX_COLORS', use_selected_to_active=False,
                )
        except RuntimeError as exc:
            return str(exc).strip().removeprefix(_ERROR_PREFIX) or "Bake failed"
        work = ground.data.color_attributes[_PASS_ATTRIBUTE_NAME]
        rgba = np.empty(len(work.data) * 4, dtype=np.float32)
        work.data.foreach_get("color", rgba)
        self._sum += rgba[0::4]
        self.done += 1
        return None

    def finish(self):
        """Write the averaged passes into the AO attribute and restore the scene."""
        colors = self.ground.data.color_attributes
        attribute = colors.get(AO_ATTRIBUTE_NAME)
        if attribute is None:
            attribute = colors.new(AO_ATTRIBUTE_NAME, 'FLOAT_COLOR', 'POINT')
        value = (self._sum / max(self.done, 1)).astype(np.float32)
        rgba = np.ones((len(value), 4), dtype=np.float32)
        rgba[:, 0] = rgba[:, 1] = rgba[:, 2] = value
        attribute.data.foreach_set("color", rgba.ravel())
        self._restore()

    def cancel(self):
        """Restore the scene and keep the AO attribute as it was."""
        if self._saved is not None:
            self._restore()

    def _restore(self):
        saved, scene = self._saved, self.scene
        self._saved = None
        scene.cycles.samples = saved["samples"]
        scene.cycles.seed = saved["seed"]
        scene.render.engine = saved["engine"]
        scene.render.bake.target = saved["target"]
        for obj in saved["hidden"]:
            obj.hide_render = False
        colors = self.ground.data.color_attributes
        work = colors.get(_PASS_ATTRIBUTE_NAME)
        if work is not None:
            colors.remove(work)
        previous = saved["active_color"]
        if previous is not None and previous in colors:
            colors.active_color = colors[previous]
        self.ground.data.update()


def bake_ground_ao(context, ground):
    """Bake AO into the ground's colorAO_id point color attribute; return an error text or None."""
    bake = AOBake(context, ground)
    error = bake.start(context)
    if error is not None:
        return error
    while bake.done < BAKE_PASSES:
        error = bake.step(context)
        if error is not None:
            bake.cancel()
            return error
    bake.finish()
    return None
