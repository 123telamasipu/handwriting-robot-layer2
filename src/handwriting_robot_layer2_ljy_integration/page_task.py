"""页面任务组织入口：把局部轨迹转换到页面坐标。"""


def layout_strokes(strokes, origin_mm=(0.0, 0.0), scale=1.0, rotation_deg=0.0):
    """第一版占位接口；正式实现需补充旋转、边界和标定变换。"""
    return {
        "origin_mm": list(origin_mm),
        "scale": scale,
        "rotation_deg": rotation_deg,
        "strokes": list(strokes),
    }
