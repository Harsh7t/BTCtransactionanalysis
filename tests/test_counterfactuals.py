from btcfusion.attribute.confidence import compute_confidence, counterfactuals


def test_counterfactuals_move_the_way_they_say():
    # Uncrowded mobile IP, and a hosting IP shared by 80 entities whose combined
    # penalty is already below the bare VPN penalty.
    for asn_type, penalty, n_ent in (("mobile", 0.9, 7), ("hosting", 0.05, 80)):
        kw = dict(base=0.6, n_obs=6, root_frac=0.4, infra_penalty=penalty,
                  tz_agreement=0.5, repeat_w=0.8)
        conf = compute_confidence(**kw)
        for cf in counterfactuals(conf, **kw, asn_type=asn_type, n_entities_on_ip=n_ent):
            if cf["direction"] == "down":
                assert cf["value"] <= round(conf, 2), (asn_type, cf, conf)
            else:
                assert cf["value"] >= round(conf, 2), (asn_type, cf, conf)
