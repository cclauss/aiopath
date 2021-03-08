from __future__ import annotations

from pathlib import _PosixFlavour, _WindowsFlavour, PurePath
from typing import Optional, Callable, Awaitable, Dict
from errno import EINVAL
import os

from aiofiles.os import wrap as wrap_async


try:
  from pathlib import _getfinalpathname
  _getfinalpathname = wrap_async(_getfinalpathname)

except ImportError:
  _getfinalpathname = None


getcwd = wrap_async(os.getcwd)


class _AsyncPosixFlavour(_PosixFlavour):
  async def gethomedir(self, username: str) -> str:
    gethomedir: Callable[[str], Awaitable[str]] = wrap_async(
      super().gethomedir
    )

    return await gethomedir(username)

  async def resolve(
    self,
    path: 'AsyncPath',
    strict: bool = False
  ) -> Optional['AsyncPath']:
      sep = self.sep
      accessor = path._accessor
      seen: Dict['AsyncPath', 'AsyncPath'] = {}

      async def _resolve(path, rest):
        if rest.startswith(sep):
          path = ''

        for name in rest.split(sep):
          if not name or name == '.':
            # current dir
            continue
          if name == '..':
              # parent dir
            path, _, _ = path.rpartition(sep)
            continue
          if path.endswith(sep):
            newpath = path + name
          else:
            newpath = path + sep + name
          if newpath in seen:
            # Already seen this path
            path = seen[newpath]
            if path is not None:
              # use cached value
              continue
            # The symlink is not resolved, so we must have a symlink loop.
            raise RuntimeError("Symlink loop from %r" % newpath)
          # Resolve the symbolic link
          try:
            target = await accessor.readlink(newpath)
          except OSError as e:
            if e.errno != EINVAL and strict:
              raise
            # Not a symlink, or non-strict mode. We just leave the path
            # untouched.
            path = newpath
          else:
            seen[newpath] = None # not resolved symlink
            path = await _resolve(path, target)
            seen[newpath] = path # resolved symlink

        return path
      # NOTE: according to POSIX, getcwd() cannot contain path components
      # which are symlinks.
      base = '' if path.is_absolute() else await getcwd()
      result = await _resolve(base, str(path))
      return result or sep


class _AsyncWindowsFlavour(_WindowsFlavour):
  async def gethomedir(self, username: str) -> str:
    gethomedir: Callable[[str], Awaitable[str]] = wrap_async(
      super().gethomedir
    )

    return await gethomedir(username)

  async def resolve(
    self,
    path: 'AsyncPath',
    strict: bool = False
  ) -> Optional['AsyncPath']:
      s = str(path)

      if not s:
          return await getcwd()

      previous_s = None

      if _getfinalpathname is not None:
        if strict:
          return self._ext_to_normal(await _getfinalpathname(s))
        else:
          tail_parts = []  # End of the path after the first one not found
          while True:
            try:
              s = self._ext_to_normal(await _getfinalpathname(s))
            except FileNotFoundError:
              previous_s = s
              s, tail = os.path.split(s)
              tail_parts.append(tail)
              if previous_s == s:
                return path
            else:
              return os.path.join(s, *reversed(tail_parts))
      # Means fallback on absolute
      return None


_async_windows_flavour = _AsyncWindowsFlavour()
_async_posix_flavour = _AsyncPosixFlavour()