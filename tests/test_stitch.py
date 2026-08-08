import pytest
from PIL import Image

from hwp2img.stitch import stitch_vertical


def test_stitch_vertical_stacks_images_top_to_bottom():
    img1 = Image.new("RGB", (100, 50), color="white")
    img2 = Image.new("RGB", (80, 60), color="black")

    result = stitch_vertical([img1, img2])

    assert result.width == 100
    assert result.height == 110
    assert result.getpixel((10, 10)) == (255, 255, 255)  # img1 영역
    assert result.getpixel((10, 70)) == (0, 0, 0)  # img2 영역


def test_stitch_vertical_single_image_passthrough():
    img = Image.new("RGB", (50, 50), color="red")

    result = stitch_vertical([img])

    assert result is img


def test_stitch_vertical_empty_list_raises():
    with pytest.raises(ValueError):
        stitch_vertical([])
