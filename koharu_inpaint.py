"""koharu와 동일한 인페인팅 경로.

참조:
  crates/koharu-pipeline/src/stages/inpainting.rs
  crates/koharu-ml/src/lama/processor.rs
  crates/koharu-ml/src/manga_text_mask/processor.rs
"""
import numpy as np
import torch
import cv2
from scipy import ndimage

TILE_SIZE = 512                     # inpainting.rs:523
TILE_CONTEXT = 128                  # inpainting.rs:524
UNIFORM_BACKGROUND_MIN_PIXELS = 16  # inpainting.rs:525
FLAT_FILL_EDGE_MARGIN = 3.0         # inpainting.rs:526

_EIGHT = np.ones((3, 3), bool)


# ---------------------------------------------------------------- 마스크 후처리
def clean_text_mask(prob, threshold=0.5, close_gaps_kernel=2,
                    fill_holes=True, padding_iterations=2):
    """manga_text_mask/processor.rs: process()"""
    m = (prob > threshold).astype(np.uint8)          # binary_mask(): 엄격한 초과
    if close_gaps_kernel > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (close_gaps_kernel | 1, close_gaps_kernel | 1))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)  # dilate 후 erode
    if fill_holes:
        m = ndimage.binary_fill_holes(m).astype(np.uint8)
    if padding_iterations > 0:
        # dilate(Norm::LInf, n) == 체비쇼프 반경 n == 3x3 정사각 n회
        m = cv2.dilate(m, np.ones((3, 3), np.uint8),
                       iterations=padding_iterations)
    return m.astype(bool)


# ---------------------------------------------------------------- flat fill
def _uniform_region_color(image, pending, region):
    """inpainting.rs:773 uniform_region_color()

    폴리곤 안 + 마스크 밖 + 테두리에서 FLAT_FILL_EDGE_MARGIN 이상 떨어진 픽셀만 샘플."""
    inner = ndimage.binary_erosion(region, iterations=int(FLAT_FILL_EDGE_MARGIN))
    sample = inner & ~pending
    if sample.sum() < UNIFORM_BACKGROUND_MIN_PIXELS:
        return None
    values = image[sample].astype(np.float64)
    median = np.median(values, axis=0)
    deviations = np.sqrt(((values - median) ** 2).mean(axis=0))
    mean_deviation = deviations.mean()
    channel_spread = np.sqrt(((deviations - mean_deviation) ** 2).mean())
    threshold = 7.0 if channel_spread > 1.0 else 10.0
    if deviations.max() >= threshold:
        return None
    return np.round(median).astype(np.uint8)


def fill_uniform_regions(output, pending, text_mask, regions):
    """inpainting.rs:590 fill_uniform_regions()"""
    filled = 0
    for region in regions:
        targets = pending & text_mask & region
        if not targets.any():
            continue
        color = _uniform_region_color(output, pending, region)
        if color is None:
            continue
        output[targets] = color
        pending[targets] = False
        filled += 1
    return filled


# ---------------------------------------------------------------- 타일 분할
def _bounds(mask_bool):
    ys, xs = np.where(mask_bool)
    return [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]


def _expand(b, width, height):
    """inpainting.rs:729 expand_bounds()"""
    return [max(b[0] - TILE_CONTEXT, 0), max(b[1] - TILE_CONTEXT, 0),
            min(b[2] + TILE_CONTEXT, width), min(b[3] + TILE_CONTEXT, height)]


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def inpaint_tiles(pending):
    """inpainting.rs:795 inpaint_tiles()"""
    labels, count = ndimage.label(pending, structure=_EIGHT)
    height, width = pending.shape
    bounded, split = [], []

    objects = ndimage.find_objects(labels)
    for index in range(1, count + 1):
        ys, xs = objects[index - 1]
        core = [xs.start, ys.start, xs.stop, ys.stop]
        left, top, right, bottom = core

        if (right - left) <= TILE_SIZE and (bottom - top) <= TILE_SIZE:
            best = None
            for position, tile in enumerate(bounded):
                merged = _union(tile["core"], core)
                if (merged[2] - merged[0]) <= TILE_SIZE and \
                   (merged[3] - merged[1]) <= TILE_SIZE:
                    growth = _area(merged) - _area(tile["core"])
                    if best is None or (growth, position) < (best[0], best[1]):
                        best = (growth, position, merged)
            if best is not None:
                _, position, merged = best
                tile = bounded[position]
                tile["components"].append(index)
                tile["core"] = merged
                tile["crop"] = _expand(merged, width, height)
            else:
                bounded.append({"components": [index], "core": core,
                                "crop": _expand(core, width, height)})
            continue

        # 512보다 큰 요소는 512 격자로 쪼갠다
        core_top = top
        while core_top < bottom:
            core_bottom = min(core_top + TILE_SIZE, bottom)
            core_left = left
            while core_left < right:
                core_right = min(core_left + TILE_SIZE, right)
                cell = labels[core_top:core_bottom, core_left:core_right] == index
                if cell.any():
                    ob = _bounds(cell)
                    owned = [ob[0] + core_left, ob[1] + core_top,
                             ob[2] + core_left, ob[3] + core_top]
                    split.append({
                        "components": [index],
                        "core": [core_left, core_top, core_right, core_bottom],
                        "crop": _expand(owned, width, height)})
                core_left = core_right
            core_top = core_bottom

    tiles = bounded + split
    tiles.sort(key=lambda t: (t["core"][1], t["core"][0],
                              t["core"][3], t["core"][2]))
    return labels, tiles


# ---------------------------------------------------------------- LaMa
def _symmetric_pad(tensor, out_h, out_w):
    """processor.rs:296 pad_img_to_modulo() — numpy 'symmetric'과 동일"""
    h, w = tensor.shape[-2:]
    yi = torch.tensor([_symmetric_index(i, h) for i in range(out_h)],
                      device=tensor.device)
    xi = torch.tensor([_symmetric_index(i, w) for i in range(out_w)],
                      device=tensor.device)
    return tensor.index_select(-2, yi).index_select(-1, xi)


def _symmetric_index(index, length):
    index = index % (length * 2)
    return index if index < length else length * 2 - index - 1


def _ceil_modulo(value, modulo=8):
    return value if value % modulo == 0 else (value // modulo + 1) * modulo


def lama_forward(model, image, mask, keep_unmasked=True):
    """processor.rs:105 pad_forward()"""
    h, w = image.shape[:2]
    device = "cuda"
    img_t = torch.from_numpy(np.ascontiguousarray(image)).to(device) \
                 .permute(2, 0, 1).unsqueeze(0)
    mask_t = torch.from_numpy(np.ascontiguousarray(mask)).to(device) \
                  .unsqueeze(0).unsqueeze(0)

    model_image = _symmetric_pad(img_t.float() / 255.0,
                                 _ceil_modulo(h), _ceil_modulo(w))
    model_mask = _symmetric_pad(mask_t.gt(0).float(),
                                _ceil_modulo(h), _ceil_modulo(w))
    with torch.no_grad():
        out = model(model_image, model_mask)
    out = out[:, :, :h, :w].clamp(0.0, 1.0) * 255.0
    out = out.to(torch.uint8)

    if keep_unmasked:
        alpha = mask_t.float() / 255.0
        out = (out.float() * alpha + img_t.float() * (1.0 - alpha)).to(torch.uint8)
    return out.squeeze(0).permute(1, 2, 0).cpu().numpy()


# ---------------------------------------------------------------- 전체
def inpaint_tiled(model, image, mask, text_mask, regions):
    """inpainting.rs:547 inpaint_tiled()"""
    output = image.copy()
    pending = mask.copy()

    filled = fill_uniform_regions(output, pending, text_mask, regions)
    labels, tiles = inpaint_tiles(pending)
    print(f"  flat_fill {filled}개 / 타일 {len(tiles)}개 / 남은 픽셀 {pending.sum()}")

    for tile in tiles:
        left, top, right, bottom = tile["crop"]
        crop_image = output[top:bottom, left:right]
        crop_mask = (pending[top:bottom, left:right]).astype(np.uint8) * 255
        if not crop_mask.any():
            continue
        generated = lama_forward(model, crop_image, crop_mask)

        # composite_generated(): 이 타일이 소유한 요소 픽셀에만 덮어쓴다
        cl, ct, cr, cb = tile["core"]
        owned = np.isin(labels[ct:cb, cl:cr], tile["components"])
        output[ct:cb, cl:cr][owned] = generated[ct - top:cb - top,
                                                cl - left:cr - left][owned]
    return output
