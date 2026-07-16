from algotrader.public_data.edgar13f import aggregate_holdings, parse_infotable

INFOTABLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>60000000000</value>
    <shrsOrPrnAmt><sshPrnamt>300000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>10000000000</value>
    <shrsOrPrnAmt><sshPrnamt>50000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>COCA COLA CO</nameOfIssuer>
    <cusip>191216100</cusip>
    <value>30000000000</value>
    <shrsOrPrnAmt><sshPrnamt>400000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parse_infotable_extracts_issuer_and_value():
    rows = parse_infotable(INFOTABLE_XML)
    assert len(rows) == 3
    assert rows[0] == {"issuer": "APPLE INC", "value": 60000000000.0}


def test_aggregate_merges_duplicate_issuers_and_computes_weights():
    total, n_positions, top = aggregate_holdings(parse_infotable(INFOTABLE_XML))
    assert total == 100000000000.0
    assert n_positions == 2  # two distinct issuers despite three rows
    assert top[0]["issuer"] == "APPLE INC"
    assert top[0]["value"] == 70000000000.0
    assert abs(top[0]["weight"] - 0.7) < 1e-9
    assert abs(sum(h["weight"] for h in top) - 1.0) < 1e-9


def test_aggregate_handles_empty_filing():
    total, n_positions, top = aggregate_holdings([])
    assert total == 0.0 and n_positions == 0 and top == []
