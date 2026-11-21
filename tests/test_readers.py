from pathlib import Path

import numpy as np
import pytest

from thermodrop.fileio.readers import DelimitedTextReader, ReaderError, default_registry


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.replace("\n", "\r\n").encode("cp1251"))
    return path


def test_semicolon_decimal_comma_with_header(tmp_path):
    path = _write(tmp_path, "a.csv", "2;3\n1,5;2,5;3,5\n4;5;6\n")
    field = DelimitedTextReader().read(path)
    assert field.data.shape == (2, 3)
    assert field.data[0, 0] == pytest.approx(1.5)


def test_tab_separated(tmp_path):
    path = _write(tmp_path, "a.txt", "2\t2\n18,7\t18,5\n17,0\t16,5\n")
    field = DelimitedTextReader().read(path)
    assert np.allclose(field.data, [[18.7, 18.5], [17.0, 16.5]])


def test_comma_separated_with_dots_no_header(tmp_path):
    path = _write(tmp_path, "a.csv", "1.0,2.0\n3.0,4.0\n")
    field = DelimitedTextReader().read(path)
    assert field.data.shape == (2, 2)


def test_whitespace_separated(tmp_path):
    path = _write(tmp_path, "a.dat", "1.0  2.0 3\n4 5 6\n")
    field = DelimitedTextReader().read(path)
    assert field.data.shape == (2, 3)


def test_ragged_rows_padded_with_nan(tmp_path):
    path = _write(tmp_path, "a.csv", "1;2;3\n4;5\n")
    field = DelimitedTextReader().read(path)
    assert np.isnan(field.data[1, 2])


def test_empty_file_raises(tmp_path):
    path = _write(tmp_path, "a.csv", "\n\n")
    with pytest.raises(ReaderError):
        DelimitedTextReader().read(path)


def test_registry_rejects_unknown_extension(tmp_path):
    with pytest.raises(ReaderError):
        default_registry().reader_for(tmp_path / "x.gtsi")
