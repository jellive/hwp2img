from PIL import Image


def stitch_vertical(images: list[Image.Image]) -> Image.Image:
    if not images:
        raise ValueError("images must not be empty")
    if len(images) == 1:
        return images[0]

    width = max(img.width for img in images)
    total_height = sum(img.height for img in images)
    canvas = Image.new("RGB", (width, total_height), color="white")

    y = 0
    for img in images:
        canvas.paste(img, (0, y))
        y += img.height
    return canvas
