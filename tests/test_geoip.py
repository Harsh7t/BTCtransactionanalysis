"""The GeoIP layer must actually use the database it says it is using.

The PS explicitly requires integrating an open-source downloadable GeoIP
database. Reporting a source in the provenance panel that is not the source
actually consulted is worse than not supporting the format at all.
"""
import ipaddress
from pathlib import Path

import numpy as np
import pytest

from btcfusion.ingest.enrich import GeoIP


def _u32(ip: str) -> int:
    return int(ipaddress.ip_address(ip))


def _table(tmp_path: Path) -> Path:
    p = tmp_path / "asn-blocks.csv"
    p.write_text(
        "cidr,asn,asn_org,asn_type,country,tz_offset_min\n"
        "198.18.0.0/16,64512,Synthetic Residential,residential,IN,330\n")
    return p


def test_table_only_resolves_from_the_table(tmp_path):
    geo = GeoIP(table_path=_table(tmp_path))
    out = geo.resolve(np.array([_u32("198.18.0.5")], dtype=np.int64))
    assert out["asn"][0] == 64512
    assert out["country"][0] == "IN"
    assert geo.source == "table:asn-blocks.csv"


def test_unknown_address_resolves_to_the_unknown_sentinel(tmp_path):
    geo = GeoIP(table_path=_table(tmp_path))
    out = geo.resolve(np.array([_u32("203.0.113.9")], dtype=np.int64))
    assert out["asn"][0] == 0
    assert out["country"][0] == "ZZ"


def test_missing_mmdb_does_not_claim_to_be_an_mmdb_source(tmp_path):
    geo = GeoIP(table_path=_table(tmp_path), mmdb_path=tmp_path / "absent.mmdb")
    assert "mmdb" not in geo.source


@pytest.mark.skipif(not list(Path("data/geo").glob("*.mmdb")),
                    reason="no .mmdb bundled; run `make geoip`")
def test_real_mmdb_is_actually_consulted():
    """A public routable address must resolve from the real database.

    Our synthetic hosts live in reserved space that no real GeoIP database has
    entries for, so a routable address is the only honest probe.
    """
    mmdb = next(iter(Path("data/geo").glob("*.mmdb")))
    geo = GeoIP(table_path=Path("data/geo/asn-blocks.csv"), mmdb_path=mmdb)
    assert geo.source.startswith("mmdb:")
    out = geo.resolve(np.array([_u32("8.8.8.8")], dtype=np.int64))
    assert out["asn"][0] != 0, "real database was opened but never consulted"


@pytest.mark.skipif(not list(Path("data/geo").glob("*.mmdb")),
                    reason="no .mmdb bundled; run `make geoip`")
def test_reserved_space_still_falls_back_to_the_bundled_table():
    """Both sources coexist: the real DB for routable IPs, the table for ours."""
    mmdb = next(iter(Path("data/geo").glob("*.mmdb")))
    geo = GeoIP(table_path=Path("data/geo/asn-blocks.csv"), mmdb_path=mmdb)
    out = geo.resolve(np.array([_u32("198.18.0.5")], dtype=np.int64))
    assert out["asn"][0] != 0, "synthetic address must still resolve via the table"
