"""Biome thumbnails: square-cropped PNGs from image files or a viewport render."""
import os
import tempfile

import bpy
import numpy

THUMBNAIL_SIZE = 512
_RENDER_RESULT = "Render Result"
_RENDER_SETTINGS = ("resolution_x", "resolution_y", "resolution_percentage")
_IMAGE_SETTINGS = ("file_format", "color_mode", "color_depth")


#----SQUARE CROP----
def write_square_png(source_path, target_path, size=THUMBNAIL_SIZE):
    """Centre-crop an image file to 1:1, shrink it to at most size and save it as PNG."""
    source = bpy.data.images.load(source_path, check_existing=False)
    square = None
    try:
        width, height = source.size
        if width == 0 or height == 0:
            raise ValueError("the image is empty or cannot be read")
        pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
        source.pixels.foreach_get(pixels)
        side = min(width, height)
        left, bottom = (width - side) // 2, (height - side) // 2
        crop = pixels.reshape(height, width, 4)[bottom:bottom + side, left:left + side]
        square = bpy.data.images.new("raf_scatter_thumbnail", side, side, alpha=True)
        square.pixels.foreach_set(numpy.ascontiguousarray(crop).ravel())
        if side > size:
            square.scale(size, size)
        square.filepath_raw = target_path
        square.file_format = 'PNG'
        square.save()
    finally:
        bpy.data.images.remove(source)
        if square is not None:
            bpy.data.images.remove(square)


#----VIEWPORT CAPTURE----
def _find_view3d(context):
    """Return (window, area, region) of the 3D viewport to capture, or None."""
    if context.area is not None and context.area.type == 'VIEW_3D':
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        return context.window, context.area, region
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                return window, area, region
    return None


def capture_viewport(context, target_path, size=THUMBNAIL_SIZE):
    """Render the 3D viewport (no overlays) to a square PNG, or raise RuntimeError."""
    found = _find_view3d(context)
    if found is None or found[2] is None:
        raise RuntimeError("no 3D viewport to capture")
    window, area, region = found
    overlay = area.spaces.active.overlay
    saved_overlays = overlay.show_overlays
    scene = context.scene
    render, image_settings = scene.render, scene.render.image_settings
    saved_render = {key: getattr(render, key) for key in _RENDER_SETTINGS}
    saved_image = {key: getattr(image_settings, key) for key in _IMAGE_SETTINGS}
    handle, temp_path = tempfile.mkstemp(suffix=".png", prefix="raf_capture_")
    os.close(handle)
    try:
        render.resolution_x = render.resolution_y = size
        render.resolution_percentage = 100
        image_settings.file_format = 'PNG'
        image_settings.color_mode = 'RGBA'
        image_settings.color_depth = '8'
        # the viewport render draws grid, gizmos and helpers unless overlays are off
        overlay.show_overlays = False
        with context.temp_override(window=window, area=area, region=region):
            bpy.ops.render.opengl(view_context=True)
        result = bpy.data.images.get(_RENDER_RESULT)
        if result is None:
            raise RuntimeError("the viewport render produced no image")
        result.save_render(temp_path, scene=scene)
        write_square_png(temp_path, target_path, size)
    except (RuntimeError, ValueError, TypeError) as error:
        raise RuntimeError(f"viewport capture failed: {error}") from error
    finally:
        overlay.show_overlays = saved_overlays
        for key, value in saved_render.items():
            setattr(render, key, value)
        for key, value in saved_image.items():
            setattr(image_settings, key, value)
        if os.path.isfile(temp_path):
            os.remove(temp_path)
