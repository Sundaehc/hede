from pathlib import Path

from fileio.image_matcher import ImageMatcher



def test_image_matcher_matches_by_exact_stem(tmp_path: Path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "ABC123.jpg"
    image_path.write_text("x", encoding="utf-8")

    matcher = ImageMatcher(image_dir)

    assert matcher.find("ABC123") == str(image_path)
    assert matcher.find("ABC") is None
