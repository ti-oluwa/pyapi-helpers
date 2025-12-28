def get_database_url(
    db_type: str,
    db_name: str,
    db_user: str,
    db_password: str,
    db_host: str,
    db_port: str,
    db_driver: str,
    **kwargs,
) -> str:
    """
    Returns a DB url based on the given parameters
    """
    query_string = (
        "?" + "&".join(f"{key}={value}" for key, value in kwargs.items())
        if kwargs
        else ""
    )
    return f"{db_type}+{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}{query_string}"
