"""Demo 3: RapidOCR 离线识别（技术验证）
验证：图片里的文字能被离线 OCR 提取（→ 进搜索索引，图片内容可被搜索）
运行：python demo3_ocr.py
"""
from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR

# 生成一张带文字的测试图（模拟报名表截图）
img = Image.new("RGB", (640, 240), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 28)
except Exception:
    font = ImageFont.load_default()
d.text((30, 40), "2026 深大新生竞赛报名", fill="black", font=font)
d.text((30, 100), "截止日期：9 月 20 日", fill="black", font=font)
d.text((30, 160), "报名方式：线上填写表格", fill="black", font=font)
path = "demo/demo3_ocr_test.png"
img.save(path)
print(f"[OK] 测试图已生成: {path}")

# 离线 OCR（不联网）
engine = RapidOCR()
result, elapse = engine(path)
texts = [line[1] for line in result] if result else []
print("[OCR] 识别耗时:", elapse)
print("[OCR] 识别结果:")
for t in texts:
    print("   ·", t)
print("[OCR] 结论:", "OK（图片文字可被搜索）" if texts else "FAIL")
