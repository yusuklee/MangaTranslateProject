import numpy as np
import cv2

#긴 상자를 줄 단위로 나눠 OCR 에 넣고, 줄 두께로 원본 글자 크기를 잰다.
#manga-ocr 은 입력을 무조건 224x224 로 줄이므로 세로 1000px 짜리 상자는 글자가 뭉개져 헛소리가 나온다.
#ctd 의 줄 맵(DBNet, 줄마다 가는 심지)으로 줄을 찾는다.

SPLIT_LIMIT = 448        # 긴 변이 이보다 크면 나눈다 (224 의 2배까지는 manga-ocr 이 버팀)
LINE_THRESHOLD = 0.5     # 줄 맵 이진화
MIN_LINE_AREA = 50       # 이보다 작은 심지는 잡음


def length(box):
    return max(box[2] - box[0], box[3] - box[1])


def thickness(box):
    return min(box[2] - box[0], box[3] - box[1])


#상자 안의 줄 상자들 (page 좌표). 줄 맵에 심지가 없으면 []
#심지는 실제 줄보다 가늘고 짧게 나온다 → 옆 심지와의 중간까지, 앞뒤로는 심지 굵기만큼 넓힌 창 안에서 잉크 범위를 잰다
def line_boxes(line_map, ink, box):
    x1, y1, x2, y2 = box
    core = (line_map[y1:y2, x1:x2] >= LINE_THRESHOLD).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(core)
    cores = [(int(x), int(y), int(x + w), int(y + h)) for x, y, w, h, a in st[1:] if a >= MIN_LINE_AREA]
    if not cores:
        return []

    sub_ink = ink[y1:y2, x1:x2]
    W, H = x2 - x1, y2 - y1
    out = []
    for cx1, cy1, cx2, cy2 in cores:
        vertical = (cy2 - cy1) > (cx2 - cx1)
        thick = (cx2 - cx1) if vertical else (cy2 - cy1)
        if vertical:
            lo, hi = 0, W                                   # 가로 한계: 옆 심지와의 중간
            for ox1, oy1, ox2, oy2 in cores:
                if (ox1, oy1, ox2, oy2) == (cx1, cy1, cx2, cy2) or oy1 >= cy2 or oy2 <= cy1:
                    continue
                if ox2 <= cx1:
                    lo = max(lo, (ox2 + cx1) // 2)
                elif ox1 >= cx2:
                    hi = min(hi, (ox1 + cx2) // 2)
            win = sub_ink[max(0, cy1 - thick):min(H, cy2 + thick), lo:hi]
            ox, oy = lo, max(0, cy1 - thick)
        else:
            lo, hi = 0, H
            for ox1, oy1, ox2, oy2 in cores:
                if (ox1, oy1, ox2, oy2) == (cx1, cy1, cx2, cy2) or ox1 >= cx2 or ox2 <= cx1:
                    continue
                if oy2 <= cy1:
                    lo = max(lo, (oy2 + cy1) // 2)
                elif oy1 >= cy2:
                    hi = min(hi, (oy1 + cy2) // 2)
            win = sub_ink[lo:hi, max(0, cx1 - thick):min(W, cx2 + thick)]
            ox, oy = max(0, cx1 - thick), lo
        ys, xs = np.nonzero(win)
        if xs.size == 0:
            out.append((x1 + cx1, y1 + cy1, x1 + cx2, y1 + cy2))
        else:
            out.append((x1 + ox + int(xs.min()), y1 + oy + int(ys.min()),
                        x1 + ox + int(xs.max()) + 1, y1 + oy + int(ys.max()) + 1))
    return out


#줄 상자들을 읽는 순서로 (재귀 XY-cut). 위아래로 갈리면 위 → 아래, 좌우로 갈리면 오른쪽 → 왼쪽 (세로쓰기)
def reading_order(boxes):
    if len(boxes) <= 1:
        return list(boxes)
    for axis, first in ((1, "top"), (0, "right")):
        lo, hi = axis, axis + 2
        order = sorted(boxes, key=lambda b: b[lo])
        end = order[0][hi]
        for k in range(1, len(order)):
            if order[k][lo] >= end:                       # 여기서 틈이 생김
                a, b = order[:k], order[k:]
                if first == "right":
                    a, b = b, a
                return reading_order(a) + reading_order(b)
            end = max(end, order[k][hi])
    #겹쳐서 못 가르면: 세로줄이 많으면 오른쪽부터, 아니면 위부터
    vertical = sum((b[3] - b[1]) > (b[2] - b[0]) for b in boxes) * 2 > len(boxes)
    return sorted(boxes, key=(lambda b: -b[2]) if vertical else (lambda b: b[1]))


#한 줄이 아직도 길면 글자 사이 빈틈(잉크 없는 행/열)에서 나눈다. 가운데 근처에서 가장 넓은 틈을 고른다
def split_long_line(ink, box, limit=SPLIT_LIMIT):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if max(w, h) <= limit:
        return [box]
    vertical = h > w
    profile = ink[y1:y2, x1:x2].sum(1 if vertical else 0)
    n = len(profile)
    lo, hi = int(n * 0.3), int(n * 0.7)          # 가운데 40% 구간에서만 자른다 (조각 크기 균형)
    best, best_w, i = None, 0, lo
    while i < hi:
        if profile[i] == 0:
            j = i
            while j < n and profile[j] == 0:
                j += 1
            if j - i > best_w:
                best, best_w = (i + j) // 2, j - i
            i = j
        else:
            i += 1
    if best is None:
        return [box]
    if vertical:
        a, b = (x1, y1, x2, y1 + best), (x1, y1 + best, x2, y2)
    else:
        a, b = (x1, y1, x1 + best, y2), (x1 + best, y1, x2, y2)
    return split_long_line(ink, a, limit) + split_long_line(ink, b, limit)


#상자 하나 → OCR 에 넣을 조각들 (읽는 순서). 짧은 상자는 그대로, 줄을 못 찾아도 그대로
def split_box(line_map, ink, box, limit=SPLIT_LIMIT):
    if length(box) <= limit:
        return [box]
    lines = reading_order(line_boxes(line_map, ink, box))
    if not lines:
        return [box]
    return [piece for line in lines for piece in split_long_line(ink, line, limit)]


#원본 글자 크기(px): 상자 안 줄들의 두께 중앙값 (세로글=열 폭, 가로글=행 높이). 줄을 못 찾으면 상자 짧은 변
def font_size(line_map, ink, box):
    lines = line_boxes(line_map, ink, box)
    return int(np.median([thickness(l) for l in lines])) if lines else thickness(box)
