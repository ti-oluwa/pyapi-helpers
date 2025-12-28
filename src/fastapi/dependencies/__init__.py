import typing
import fastapi.params


def Dependency(
    dep: typing.Union[typing.Callable, fastapi.params.Depends],
) -> fastapi.params.Depends:
    """FastAPI dependency decorator"""
    if isinstance(dep, fastapi.params.Depends):
        return dep
    return fastapi.Depends(dep)
