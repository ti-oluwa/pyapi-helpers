from typing import Optional
import io
import os
from django.core.files import File as DjangoFile
from django.core.files.uploadedfile import InMemoryUploadedFile

from src.generics.utils.misc import (
    str_is_base64,
    bytes_is_base64,
    bytes_to_base64,
    str_to_base64,
)
from src.dependencies import depends_on
from .files import download, _File


@depends_on({"PIL": "Pillow"})
def compress_image(
    image: DjangoFile, *, quality: int = 90, format: Optional[str] = None
) -> InMemoryUploadedFile:
    """
    Compress an image by adjusting the quality and format.

    :param image: The image file to compress.
    :param quality: The quality of the compression. Default is 90.
    :param format: The format of the image. Default is None.
    """
    from PIL import Image

    img = Image.open(image)
    img_io = io.BytesIO()
    img_name = image.name
    in_memory_file = InMemoryUploadedFile(
        file=img_io,
        field_name=None,
        name=img_name,
        content_type=None,
        size=img_io.getbuffer().nbytes,
        charset=None,
    )
    img.save(in_memory_file, format=format, quality=quality)
    return in_memory_file


@depends_on({"PIL": "Pillow"})
def enhance_image(
    image: DjangoFile,
    *,
    contrast: float = 1.1,
    sharpness: float = 1.1,
    color: float = 1.02,
    brightness: float = 1.0,
) -> InMemoryUploadedFile:
    """
    Enhance an image by adjusting contrast, sharpness, color and brightness.

    :param image: The image file to enhance.
    :param contrast: The contrast factor. Default is 1.1.
    :param sharpness: The sharpness factor. Default is 1.1.
    :param color: The color factor. Default is 1.02.
    :param brightness: The brightness factor. Default is 1.0.
    :return: An enhanced image as an InMemoryUploadedFile.
    """
    from PIL import Image, ImageEnhance

    img = Image.open(image)
    img_io = io.BytesIO()

    # Enhance contrast
    img = ImageEnhance.Contrast(img).enhance(contrast)
    # Enhance sharpness
    img = ImageEnhance.Sharpness(img).enhance(sharpness)
    # Enhance color
    img = ImageEnhance.Color(img).enhance(color)
    # Enhance brightness
    img = ImageEnhance.Brightness(img).enhance(brightness)

    img_name = image.name
    in_memory_file = InMemoryUploadedFile(
        file=img_io,
        field_name=None,
        name=img_name,
        content_type=None,
        size=img_io.getbuffer().nbytes,
        charset=None,
    )
    img.save(in_memory_file)
    return in_memory_file


@depends_on({"cv2": "opencv-python-headless", "numpy": "numpy"})
def denoise_image(image: DjangoFile) -> InMemoryUploadedFile:
    """
    Denoise an image using histogram equalization and non-local means denoising.

    This reduces noise in the image and enhances the overall quality.

    Uses OpenCV for image processing. Run `pip install opencv-python-headless` to install.

    :param image: The image file to denoise.
    :return: A denoised image as an InMemoryUploadedFile.
    """
    import cv2
    import numpy as np

    # Check if image is a DjangoFile or BytesIO and read the buffer correctly
    if isinstance(image, io.BytesIO):
        buffer = image.getvalue()
    else:
        image.file.seek(0)
        buffer = image.file.read()

    # Load the image using OpenCV from BytesIO buffer
    img_array = np.frombuffer(buffer, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(
            "Image decoding failed. Ensure the input is a valid image file."
        )

    # Convert to YUV color space
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)

    # Apply histogram equalization on the Y channel
    yuv[:, :, 0] = cv2.equalizeHist(yuv[:, :, 0])

    # Convert back to BGR color space
    img = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)

    # Denoise the image with reduced strength
    img = cv2.fastNlMeansDenoisingColored(
        src=img, dst=None, h=3, hColor=3, templateWindowSize=7, searchWindowSize=21
    )

    # Determine file extension
    _, ext = os.path.splitext(image.name)
    ext = ext.lower() if ext else ".jpg"  # Default to .jpg if no extension found

    # Encode the enhanced image to the correct format
    success, encoded_image = cv2.imencode(ext, img)
    if not success:
        raise ValueError("Image encoding failed. Ensure the output format is correct.")

    # Save the enhanced image to a BytesIO object
    img_io = io.BytesIO(encoded_image.tobytes())
    img_name = image.name
    # Return an InMemoryUploadedFile
    return InMemoryUploadedFile(
        file=img_io,
        field_name=None,
        name=img_name,
        content_type=None,
        size=img_io.getbuffer().nbytes,
        charset=None,
    )


def file_to_base64(file: _File) -> str:
    """
    Convert a file to a base64 encoded string.

    Supports file paths, bytes, BytesIO and Django File objects.
    """
    if isinstance(file, str):
        if str_is_base64(file):
            return file
        elif file.startswith("http"):
            return bytes_to_base64(download(file))
        elif os.path.exists(file):
            with open(file, mode="rb") as file:
                return bytes_to_base64(file.read())
        else:
            return str_to_base64(file)

    elif isinstance(file, bytes):
        if bytes_is_base64(file):
            return file
        else:
            return bytes_to_base64(file)

    elif isinstance(file, io.BytesIO):
        return bytes_to_base64(file.getvalue())

    elif isinstance(file, DjangoFile):
        file.open()
        file.file.seek(0)
        return bytes_to_base64(file.file.read())
    raise ValueError(f"Invalid type for file '{type(file).__name__}'")
