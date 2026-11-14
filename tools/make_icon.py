"""Generates assets/icon.ico and assets/icon.png (run once; needs Pillow)."""
import os
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=(31, 111, 235, 255))
# hard-disk platter
d.ellipse((212, 212, 812, 812), fill=(255, 255, 255, 255))
d.ellipse((432, 432, 592, 592), fill=(31, 111, 235, 255))
# recovery arrow: an arc with an arrow head, cut out of the platter
d.arc((292, 292, 732, 732), start=200, end=20, fill=(31, 111, 235, 255), width=46)
d.polygon([(735, 395), (790, 560), (640, 520)], fill=(31, 111, 235, 255))
os.makedirs("assets", exist_ok=True)
img.resize((256, 256), Image.LANCZOS).save("assets/icon.png")
img.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
