import io
import unittest

from app.ftp_guard import ReadOnlyFTP, WriteBlockedError
from tests.fake_ftp import FakeFTP


class FtpGuardTests(unittest.TestCase):
    def test_read_only_blocks_mkd_and_stor(self):
        inner = FakeFTP({"Work Orders": {}})
        inner.parts = ["Work Orders"]
        guarded = ReadOnlyFTP(inner, read_only=True)
        with self.assertRaises(WriteBlockedError):
            guarded.mkd("RK-New")
        with self.assertRaises(WriteBlockedError):
            guarded.storbinary("STOR file.txt", io.BytesIO(b"x"))


if __name__ == "__main__":
    unittest.main()
