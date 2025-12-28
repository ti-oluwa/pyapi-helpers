import string
import random
import os


def generate_unique_identifier(length: int = 12) -> str:
    """Generate a unique identifier of the specified length"""
    st = string.ascii_letters + string.digits
    count = 0
    code = ""
    while count != length:
        for _ in range(3):
            code += random.choice(st)
            count += 1
        if count != length:
            code += "-"
    return code


def random_hex(length: int = 12) -> str:
    """Generate a unique hex of the specified length"""
    return os.urandom(length).hex()
