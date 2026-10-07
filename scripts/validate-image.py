"""Decode and normalize supported reference images in the document runtime."""
import sys,warnings
from PIL import Image,ImageOps
Image.MAX_IMAGE_PIXELS=16000000
warnings.simplefilter('error',Image.DecompressionBombWarning)
with Image.open(sys.argv[1]) as image:
    if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16000000:raise ValueError('Unsupported image')
    image.load();ImageOps.exif_transpose(image).convert('RGBA').save(sys.argv[2],format='PNG')
from pathlib import Path
if Path(sys.argv[2]).stat().st_size>20*1024**2:raise ValueError('Normalized image too large')
