"""The generator must produce identical bytes for identical seeds.

This is the one property the whole reproducibility claim rests on, and it was
false: `actor_ip_for` selected an actor's announcing IP with Python's built-in
`hash()` on a string. String hashing is randomised per process unless
PYTHONHASHSEED is pinned, so two runs at the same --seed agreed on every column
except `src_ip` - the network half of the thesis, and the column every
attribution figure is computed from.

Testing it by generating twice inside ONE process would prove nothing: hash
randomisation is fixed for a process's lifetime, so the bug is invisible there.
Instead we pin the selection to a golden value. crc32 is stable across
processes and machines, so this passes forever; `hash()` returns a different
value in almost every process, so a regression fails immediately.
"""
from __future__ import annotations

import subprocess
import sys
import zlib

import numpy as np

from btcfusion.generator.model import Actor
from btcfusion.generator.network import AddressSpace, SharedInfrastructure, actor_ip_for


def _actor(eid: str, n_ips: int = 4) -> Actor:
    return Actor(eid=eid, archetype="mixer", script_type="p2wpkh",
                 ips=[f"198.51.100.{i}" for i in range(n_ips)],
                 asn=64500, country="UA", asn_type="hosting")


def _shared() -> SharedInfrastructure:
    rng = np.random.default_rng(0)
    return SharedInfrastructure(AddressSpace(rng), rng, size=4)


def test_ip_selection_is_a_pure_function_of_the_entity_id():
    """Same entity, same day -> same IP, in any process."""
    shared = _shared()
    rng = np.random.default_rng(0)
    a = _actor("ENT-00042")
    day = 20000
    ts = day * 86400

    # The index the implementation must compute, spelled out independently.
    expected = (day * 1103515245 + zlib.crc32(b"ENT-00042")) % 4
    ip, *_ = actor_ip_for(a, ts, shared, rng, churn_prob=0.0)
    assert ip == a.ips[expected], (
        "IP selection is not a stable function of the entity id - if this uses "
        "hash() again, generation is no longer reproducible across processes")


def test_two_processes_agree_on_the_selection():
    """The property that actually matters, measured across a process boundary."""
    code = (
        "import numpy as np;"
        "from btcfusion.generator.model import Actor;"
        "from btcfusion.generator.network import AddressSpace, SharedInfrastructure, actor_ip_for;"
        "a=Actor(eid='ENT-00042',archetype='mixer',script_type='p2wpkh',"
        "ips=['198.51.100.%d'%i for i in range(4)],asn=64500,country='UA',asn_type='hosting');"
        "r=np.random.default_rng(0);s=SharedInfrastructure(AddressSpace(r),r,4);"
        "print(actor_ip_for(a,20000*86400,s,np.random.default_rng(0),0.0)[0])"
    )
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, check=True).stdout.strip()
            for _ in range(3)}
    assert len(runs) == 1, f"IP selection differs between processes: {runs}"


def test_truth_mapping_breaks_ties_deterministically():
    """A cluster split evenly between two true entities must always label the same.

    `map_to_truth` used `sort(...).group_by(...).first()` with no tie-break and
    no maintain_order. Polars guarantees neither ordering, and both are threaded,
    so an ambiguous cluster took whichever label the run happened to produce.
    Measured before the fix: two identical training runs disagreed on ~9 entities
    and every metric graded against those labels moved with them.
    """
    import polars as pl

    from btcfusion.eval.labels import map_to_truth

    # ENT-1 owns two addresses, one from each true entity: a perfect tie.
    addr_map = pl.DataFrame({"entity_id": ["ENT-1", "ENT-1"], "address": ["a", "b"]})
    truth_addr = pl.DataFrame({"address": ["a", "b"], "eid": ["TRUE-B", "TRUE-A"]})
    truth_ent = pl.DataFrame({
        "eid": ["TRUE-A", "TRUE-B"], "illicit": [0, 1],
        "typology": ["", "layering"], "archetype": ["exchange", "mixer"]})

    seen = {map_to_truth(addr_map, truth_addr, truth_ent)[0]
            .get_column("true_eid")[0] for _ in range(8)}
    assert seen == {"TRUE-A"}, (
        f"ambiguous cluster resolved inconsistently: {seen} - ties must break on "
        "the true entity id so ground truth is reproducible")


def test_transaction_matrix_row_order_is_total():
    """The transaction head holds out a fraction of rows AS ORDERED."""
    import datetime as dt

    import polars as pl

    from btcfusion.features.extract import transaction_feature_matrix

    txs = pl.DataFrame({
        "txid": ["c", "a", "b"],
        "timestamp": [dt.datetime(2026, 6, 1, 0, 0)] * 3,
        "sender_entity": ["ENT-1"] * 3,
        "receiver_entities": [["ENT-2"]] * 3,
        "input_addresses": [["x"]] * 3, "output_addresses": [["y"]] * 3,
        "input_amounts": [[10]] * 3, "output_amounts": [[9]] * 3,
        "fee": [1, 1, 1], "script_type": ["p2wpkh"] * 3,
        "hour_utc": [0, 0, 0], "weekday": [0, 0, 0],
    })
    fm = pl.DataFrame({"entity": ["ENT-1"], "n_tx_sent": [3.0]})
    m, _ = transaction_feature_matrix(txs, fm, {"ENT-1": 0.5})
    assert m.get_column("txid").to_list() == ["a", "b", "c"]
