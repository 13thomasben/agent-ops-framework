from brief.reply_close import parse_positions


def test_basic():
    assert parse_positions("close 4, 7") == [4, 7]


def test_variants():
    assert parse_positions("Close #4") == [4]
    assert parse_positions("close 4 7 and 9") == [4, 7, 9]
    assert parse_positions("close 2; 3") == [2, 3]
    assert parse_positions("CLOSE: 1") == [1]


def test_ignores_quoted_original():
    body = "close 3\n\nFrom: Accountability Brief\n...close 4, 7 example text..."
    assert parse_positions(body) == [3]


def test_no_directive():
    assert parse_positions("thanks, looks right today") == []
    assert parse_positions("") == []
    # numbers without the word 'close' are not a close directive
    assert parse_positions("4 and 7 look wrong") == []
