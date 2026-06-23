import industriax


def test_package_imports_and_has_version():
    assert isinstance(industriax.__version__, str)
    assert industriax.__version__  # 非空
