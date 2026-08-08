from hwp2img.pdf_to_images import render_pages


def test_render_pages_returns_one_image_per_page(make_pdf):
    pdf_path = make_pdf(page_count=3)

    images = render_pages(pdf_path)

    assert len(images) == 3


def test_render_pages_respects_dpi(make_pdf):
    pdf_path = make_pdf(page_count=1, width=200, height=300)

    images_low = render_pages(pdf_path, dpi=72)
    images_high = render_pages(pdf_path, dpi=200)

    assert images_high[0].width > images_low[0].width
    assert images_high[0].height > images_low[0].height
