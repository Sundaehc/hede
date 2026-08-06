from pathlib import Path
from types import SimpleNamespace

from api.routes.images import image_url_for


def test_image_url_accepts_a_historical_unc_alias_for_the_same_root_folder():
    settings = SimpleNamespace(
        image_roots={
            "smiley": Path(r"\\192.168.10.229\图片\产品45主图随时更新\45主图\笑脸45度图"),
        }
    )

    image_url = image_url_for(
        "smiley",
        r"\\Hede\图片\产品45主图随时更新\45主图\笑脸45度图\S100.jpg",
        settings,
    )

    assert image_url == "/images/serve/smiley/S100.jpg"


def test_image_url_for_ni_uses_the_ni_image_root():
    settings = SimpleNamespace(
        image_roots={
            "ni": Path(r"\\192.168.10.229\图片\产品45主图随时更新\45主图\NI图片"),
        }
    )

    image_url = image_url_for(
        "ni",
        r"\\192.168.10.229\图片\产品45主图随时更新\45主图\NI图片\NI22Q3A010101.jpg",
        settings,
    )

    assert image_url == "/images/serve/ni/NI22Q3A010101.jpg"
