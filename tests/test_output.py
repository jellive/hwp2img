from PIL import Image

from hwp2img.output import save_result


def test_save_result_writes_png_named_after_source(tmp_path):
    image = Image.new("RGB", (10, 10), color="white")
    output_dir = tmp_path / "변환된사진"

    out_path = save_result(image, "/원본/공문_2026.hwp", str(output_dir))

    assert out_path == str(output_dir / "공문_2026_변환.png")
    assert (output_dir / "공문_2026_변환.png").exists()


def test_save_result_creates_output_dir_if_missing(tmp_path):
    image = Image.new("RGB", (10, 10), color="white")
    output_dir = tmp_path / "does" / "not" / "exist"

    save_result(image, "doc.hwp", str(output_dir))

    assert output_dir.is_dir()
