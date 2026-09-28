"""In-memory FTP stand-in for upload tests."""

from __future__ import annotations

from ftplib import error_perm


class FakeFTP:
    def __init__(self, tree: dict):
        self.tree = tree
        self.parts: list[str] = []
        self.mkd_calls: list[str] = []
        self.stored: list[tuple[str, bytes]] = []

    def pwd(self) -> str:
        if not self.parts:
            return "/"
        return "/" + "/".join(self.parts)

    def _node(self) -> dict:
        node = self.tree
        for part in self.parts:
            value = node.get(part)
            if not isinstance(value, dict):
                raise error_perm("550")
            node = value
        return node

    def cwd(self, name: str) -> None:
        if name == "..":
            if not self.parts:
                raise error_perm("550")
            self.parts.pop()
            return
        if name.startswith("/"):
            parts = [part for part in name.split("/") if part]
            node = self.tree
            for part in parts:
                value = node.get(part)
                if not isinstance(value, dict):
                    raise error_perm("550")
                node = value
            self.parts = parts
            return
        node = self._node()
        if not isinstance(node.get(name), dict):
            raise error_perm("550")
        self.parts.append(name)

    def mlsd(self):
        for name, value in self._node().items():
            kind = "dir" if isinstance(value, dict) else "file"
            yield name, {"type": kind}

    def nlst(self) -> list[str]:
        return list(self._node().keys())

    def mkd(self, name: str) -> None:
        self._node()[name] = {}
        self.mkd_calls.append(f"{self.pwd().rstrip('/')}/{name}")

    def storbinary(self, command: str, handle) -> None:
        filename = command.split(" ", 1)[1]
        payload = handle.read()
        self._node()[filename] = payload
        self.stored.append((f"{self.pwd().rstrip('/')}/{filename}", payload))

    def quit(self) -> None:
        return None

    def close(self) -> None:
        return None
