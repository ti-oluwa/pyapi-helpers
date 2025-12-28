import secrets


def generate_secure_password(length=12):
    # Use Django's get_random_string for generating a password and secrets for security
    allowed_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+"
    )
    return "".join(secrets.choice(allowed_chars) for _ in range(length))
