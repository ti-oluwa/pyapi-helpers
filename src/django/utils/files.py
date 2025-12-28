import functools
import mimetypes
import imghdr
import os
from io import BytesIO
from pathlib import Path
import typing
import asyncio
from django.core.files import File as DjangoFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from asgiref.sync import sync_to_async

from src.generics.utils.downloads import download, async_download


class Response(typing.Protocol):
    """Interface for a response object"""

    content: bytes
    headers: typing.Mapping[str, str]
    url: str
    charset_encoding: str


def response_to_in_memory_file(response: Response) -> InMemoryUploadedFile:
    """Download response handler. Returns response content as an `InMemoryUploadedFile`"""
    url = response.url
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    charset = response.charset_encoding
    file_io = BytesIO(response.content)
    file_name = url.path.split("/")[-1]
    return InMemoryUploadedFile(
        file_io,
        field_name=None,
        name=file_name,
        content_type=content_type,
        size=file_io.getbuffer().nbytes,
        charset=charset,
    )


download_file = functools.partial(download, handler=response_to_in_memory_file)
"""Download url content as an `InMemoryUploadedFile`"""

async_download_file = functools.partial(
    async_download, handler=sync_to_async(response_to_in_memory_file)
)
"""Download url content as an `InMemoryUploadedFile`"""


IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "svg", "ico")
VIDEO_EXTENSIONS = ("mp4", "webm", "mkv", "flv", "avi", "mov", "wmv", "mpg", "mpeg")
AUDIO_EXTENSIONS = ("mp3", "wav", "ogg", "flac", "aac", "wma", "m4a", "opus")


def infer_file_type(file: typing.Union[str, DjangoFile]) -> str:
    """
    Infers the type of a file (video, image, audio, ...) based on its content or extension.

    :param file: The path to the file whose type needs to be determined.

    :return: The inferred file type, which can be "video", "image", "audio", "<ext>" or "unknown"
         if the file type cannot be determined.
    """
    # Check if it's an image by inspecting the file header
    if imghdr.what(file):
        return "image"

    # Infer file type using the MIME type based on file extension
    if isinstance(file, DjangoFile):
        file = file.name

    mime_type, _ = mimetypes.guess_type(file)
    if mime_type:
        if mime_type.startswith("video"):
            return "video"
        elif mime_type.startswith("audio"):
            return "audio"

    return infer_file_type_from_extension(file)


def infer_file_type_from_extension(file: str):
    """
    Infers the type of a file (video, image, audio, ...) based on its extension.

    :param file: The path to the file whose type needs to be determined.

    :return: The inferred file type, which can be "video", "image", "audio", "<ext>" or "unknown"
         if the file type cannot be determined.
    """
    _, ext = os.path.splitext(file)
    if ext:
        ext = ext[1:].lower()
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in VIDEO_EXTENSIONS:
            return "video"
        if ext in AUDIO_EXTENSIONS:
            return "audio"
        return ext

    return "unknown"


def find_files_by_extension(
    directory: str, extensions: typing.Iterable[str], search_sub_dirs: bool = False
) -> typing.Dict[str, typing.List[Path]]:
    """
    Finds all files with specified extensions in a directory.
    Groups files found by extension.

    :param directory: The directory to search for files.
    :param search_sub_dirs: Whether to search subdirectories.
    :param extensions: A tuple of file extensions to search for.

    :return: A mapping of file extensions to a list of file paths.
    """
    files = {}
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid directory: {directory}")

    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            ext = ext[1:].lower()
            if ext in extensions:
                path = Path(os.path.join(root, filename)).resolve()
                files.setdefault(ext, []).append(path)

        if not search_sub_dirs:
            break
    return files


def load_file_to_memory(path: typing.Union[Path, str]) -> InMemoryUploadedFile:
    """
    Loads a file from disk into memory as an `InMemoryUploadedFile`.

    :param path: The path to the file.

    :return: The file as an `InMemoryUploadedFile`.
    """
    with open(path, "rb") as file:
        file_io = BytesIO(file.read())
        return InMemoryUploadedFile(
            file_io,
            field_name=None,
            name=path.name,
            content_type=mimetypes.guess_type(path.name)[0],
            size=file_io.getbuffer().nbytes,
            charset=None,
        )


def load_files_to_memory(
    paths: typing.List[typing.Union[Path, str]],
) -> typing.List[InMemoryUploadedFile]:
    """
    Loads multiple files from disk into memory as `InMemoryUploadedFile` objects.

    :param paths: A list of paths to the files.
    :return: A list of `InMemoryUploadedFile` objects.
    """
    if not paths:
        return []

    # If there's only one path, there's no need to run async code
    if len(paths) == 1:
        return [load_file_to_memory(paths[0])]

    async def main():
        async_load_file = sync_to_async(load_file_to_memory)
        tasks = []
        for path in paths:
            task = asyncio.create_task(async_load_file(path))
            tasks.append(task)
        return await asyncio.gather(*tasks)

    return list(asyncio.run(main()))


__all__ = [
    "download_file",
    "async_download_file",
    "infer_file_type",
    "infer_file_type_from_extension",
    "find_files_by_extension",
    "load_file_to_memory",
    "load_files_to_memory",
]
