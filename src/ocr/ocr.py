"""拾光 · OCR 模块：RapidOCR 离线识别（图片文字 → 搜索索引）

- 首次调用才初始化引擎（启动快）
- 大图先压缩到最长边 1600px 再识别（提速，精度几乎无损）
"""
import os

from PIL import Image

MAX_SIDE = 1600
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def ocr_image(path):
    """识别图片中的文字，返回字符串（多行用换行连接）；无文字返回空串"""
    tmp = None
    try:
        img = Image.open(path)
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            tmp = path + ".sg_tmp.jpg"
            img.convert("RGB").save(tmp, quality=90)
            target = tmp
        else:
            target = path
        result, _ = _get_engine()(target)
        if not result:
            return ""
        return "\n".join(str(line[1]) for line in result)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    import sys
    print(ocr_image(sys.argv[1] if len(sys.argv) > 1 else "demo/demo3_ocr_test.png"))
