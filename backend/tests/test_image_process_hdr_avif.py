import json
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

from app.utils.image_process import inspect_avif_hdr_metadata, save_hdr_avif_image


@unittest.skipUnless(imagecodecs is not None and np is not None, "imagecodecs/numpy not available")
class SaveHdrAvifImageTests(unittest.TestCase):
    def test_jxr_transcodes_to_complete_hdr_avif(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory(prefix="agms-hdr-avif-test-") as temp_dir:
            output_path = Path(temp_dir) / "sample.avif"
            save_hdr_avif_image(self._build_synthetic_jxr(), output_path)

            raw = output_path.read_bytes()
            self.assertTrue(imagecodecs.avif_check(raw))

            metadata = inspect_avif_hdr_metadata(raw)
            self.assertIn("nclx", metadata.associated_property_types)
            self.assertIn("mdcv", metadata.associated_property_types)
            self.assertIn("clli", metadata.associated_property_types)
            self.assertEqual(metadata.color_primaries, 9)
            self.assertEqual(metadata.transfer_characteristics, 16)
            self.assertEqual(metadata.matrix_coefficients, 9)
            self.assertFalse(metadata.full_range)
            self.assertTrue(metadata.has_mastering_display_metadata)
            self.assertTrue(metadata.has_content_light_level_metadata)
            self.assertGreater(metadata.max_content_light_level, 0)
            self.assertGreater(metadata.max_pic_average_light_level, 0)

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
                stream = json.loads(probe.stdout)["streams"][0]
                self.assertEqual(stream["color_space"], "bt2020nc")
                self.assertEqual(stream["color_transfer"], "smpte2084")
                self.assertEqual(stream["color_primaries"], "bt2020")

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
