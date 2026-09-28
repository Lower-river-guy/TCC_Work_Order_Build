"""FTP wrapper that blocks write operations in dry-run / read-only mode."""

from __future__ import annotations

from ftplib import FTP


class WriteBlockedError(RuntimeError):
    """Raised when a dry-run session attempts an FTP write."""


class ReadOnlyFTP:
    """Proxy around ftplib.FTP that rejects MKD and STOR while read_only is True."""

    def __init__(self, ftp: FTP, read_only: bool):
        self._ftp = ftp
        self.read_only = read_only

    def __getattr__(self, name: str):
        return getattr(self._ftp, name)

    def mkd(self, dirname: str) -> str:
        if self.read_only:
            raise WriteBlockedError("FTP MKD is blocked while dry_run is enabled.")
        return self._ftp.mkd(dirname)

    def storbinary(self, cmd: str, fp, blocksize: int = 8192, callback=None, rest=None):
        if self.read_only:
            raise WriteBlockedError("FTP STOR is blocked while dry_run is enabled.")
        return self._ftp.storbinary(cmd, fp, blocksize, callback, rest)

    def quit(self):
        return self._ftp.quit()

    def close(self):
        return self._ftp.close()
