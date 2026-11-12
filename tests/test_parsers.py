"""Parsers for the NOAA text formats (sample lines copied in the published layout)."""
import pandas as pd

from sentinel.fetch import _chunks, parse_dmi, parse_oni

ONI_SAMPLE = """ SEAS  YR   TOTAL   ANOM
  DJF 1997  25.61  -0.47
  NDJ 1997  28.84   2.24
  DJF 1998  28.73   2.24
"""

DMI_SAMPLE = """ 1870 2026
 1997   -0.110   -0.050    0.020    0.130    0.210    0.310    0.420    0.690    0.860    1.020    0.790    0.410
 2026    0.050    0.010 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000
  -9999
  DMI HadISST1.1  missing value -9999
"""


def test_parse_oni_centres_seasons():
    d = parse_oni(ONI_SAMPLE)
    assert d.set_index("date").loc[pd.Timestamp("1997-12-01"), "oni"] == 2.24   # NDJ -> Dec
    assert d.set_index("date").loc[pd.Timestamp("1998-01-01"), "oni"] == 2.24   # DJF -> Jan
    assert len(d) == 3


def test_parse_dmi_skips_missing_and_footer():
    d = parse_dmi(DMI_SAMPLE).set_index("date")
    assert d.loc[pd.Timestamp("1997-10-01"), "dmi"] == 1.02
    assert pd.Timestamp("2026-03-01") not in d.index and len(d) == 14


def test_chunks_cover_range_without_gaps():
    ch = list(_chunks("1991-01-01", "2026-11-05", years=5))
    assert ch[0][0] == "1991-01-01" and ch[-1][1] == "2026-11-05"
    for (_, e), (s, _) in zip(ch, ch[1:]):
        assert pd.Timestamp(s) - pd.Timestamp(e) == pd.Timedelta(days=1)
