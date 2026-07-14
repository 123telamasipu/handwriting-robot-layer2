"""统一轨迹导出入口，后续接入 SVG/G-code 导出器。"""


def export_strokes(document: dict) -> dict:
    """校验并返回设备层可消费的有序轨迹。"""
    if document.get("schema_version") is None:
        raise ValueError("stroke document requires schema_version")
    if "strokes" not in document:
        raise ValueError("stroke document requires strokes")
    return {"schema_version": document["schema_version"], "strokes": document["strokes"]}
