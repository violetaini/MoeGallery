import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import imagecodecs
    import numpy as np
except ImportError:
    imagecodecs = None
    np = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.image_process import save_hdr_avif_image


@unittest.skipUnless(imagecodecs is not None and np is not None, "imagecodecs/numpy not available")
class SaveHdrAvifImageTests(unittest.TestCase):
    def test_jxr_transcodes_to_complete_hdr_avif(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory(prefix="agms-hdr-avif-test-") as temp_dir:
            output_path = Path(temp_dir) / "sample.avif"
            save_hdr_avif_image(self._build_synthetic_jxr(), output_path)

            raw = output_path.read_bytes()
            self.assertNotEqual(raw.find(b"nclx"), -1)
            self.assertNotEqual(raw.find(b"mdcv"), -1)
            self.assertNotEqual(raw.find(b"clli"), -1)
            self.assertTrue(imagecodecs.avif_check(raw))

            decoded = imagecodecs.avif_decode(raw)
            self.assertEqual(decoded.shape, (128, 256, 3))
            self.assertEqual(str(decoded.dtype), "uint16")

            ffprobe = shutil.which("ffprobe")
            if ffprobe:
                probe = subprocess.run(
                    [
                        ffprobe,
                        "-hide_banner",
                        "-show_streams",
                        "-print_format",
                        "json",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("Mastering display metadata", probe.stdout)
                self.assertIn("Content light level metadata", probe.stdout)

    @staticmethod
    def _build_synthetic_jxr() -> bytes:
        h, w = 128, 256
        x = np.linspace(0.0, 6.0, w, dtype=np.float32)
        y = np.linspace(0.0, 2.0, h, dtype=np.float32)[:, None]
        r = np.broadcast_to(x, (h, w))
        g = np.broadcast_to(y, (h, w))
        b = np.sqrt(np.maximum(r + g, 0.0))
        a = np.ones((h, w), dtype=np.float32)
        rgba = np.stack([r, g, b, a], axis=-1).astype(np.float16)
        return imagecodecs.jpegxr_encode(rgba)


if __name__ == "__main__":
    unittest.main()
