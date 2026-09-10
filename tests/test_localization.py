from amap_tool.localization import normalize_language, text


def test_language_normalization_and_fallback():
    assert normalize_language("zh-CN") == "zh_CN"
    assert normalize_language("en-GB") == "en_US"
    assert normalize_language("unknown") == "zh_CN"
    assert text("en_US", "open_folder") == "Open Folder"
    assert text("zh_CN", "open_folder") == "打开文件夹"
    assert text("zh_CN", "unknown_key") == "unknown_key"


def test_localized_dynamic_text_keeps_machine_values_out_of_translation():
    assert text("zh_CN", "image_navigation", index=2, total=9, image_id="campus_001") == "  图片 2/9: campus_001"
    assert text("en_US", "zoom", percent=200) == "Zoom: 200%"
