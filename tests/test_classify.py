from gpcheck.classify.cookies import CookieDB, is_tracking_cookie, seed_cookie_db
from gpcheck.classify.domains import EntityMap, etld1
from gpcheck.classify.signals import declared_signals, parse_gpp, parse_optanon, parse_usp
from gpcheck.classify.trackers import build_tracker_list


def test_etld1():
    assert etld1("www.bbc.co.uk") == "bbc.co.uk"
    assert etld1("a.b.example.com") == "example.com"
    assert etld1("cdn.honors.test") == "honors.test"
    assert etld1("127.0.0.1") == "127.0.0.1"


def test_entity_same_party():
    tl = build_tracker_list()
    assert not tl.entities.is_third_party("www.youtube.com", "www.google.com")
    assert tl.entities.is_third_party("connect.facebook.net", "www.nytimes.com")
    assert not EntityMap().is_third_party("cdn.example.com", "www.example.com")


def test_tracker_match_parent_domains():
    tl = build_tracker_list()
    assert tl.match("stats.g.doubleclick.net")
    assert tl.owner("stats.g.doubleclick.net") == "Google"
    assert tl.match("www.example.com") is None


def test_usp():
    assert parse_usp("1YYN")["opted_out"] is True
    assert parse_usp("1YNN")["opted_out"] is False
    assert parse_usp("1---") is None


def test_gpp_usnat():
    ping = {"gppString": "x", "parsedSections": {"usnat": {"SaleOptOut": 1, "SharingOptOut": 1, "Gpc": True}}}
    assert parse_gpp(ping)["opted_out"] is True
    assert parse_gpp(ping)["gpc_flag"] is True
    assert parse_gpp({"parsedSections": {"usnat": {"SaleOptOut": 2}}})["opted_out"] is False


def test_optanon():
    o = parse_optanon("isGpcEnabled=1&datestamp=x&groups=C0001%3A1%2CC0004%3A0")
    assert o["gpc_enabled"] is True and o["targeting_off"] is True


def test_declared_signals_combines_sources():
    rec = {"signals": {"usp": {"uspString": "1YYN"}, "gpc_json": {"gpc": True}}, "cookies": []}
    d = declared_signals(rec)
    assert d["declared_optout"] is True and d["gpc_json_support"] is True
    assert declared_signals({"signals": {}, "cookies": []})["declared_optout"] is None


def test_tracking_cookies():
    tl = build_tracker_list()
    db = seed_cookie_db()
    assert is_tracking_cookie({"name": "_ga_ABC123", "domain": ".example.com"}, "example.com", db, tl, tl.entities)
    assert is_tracking_cookie({"name": "whatever", "domain": ".doubleclick.net"}, "example.com", db, tl, tl.entities)
    assert not is_tracking_cookie({"name": "session", "domain": "example.com"}, "example.com", db, tl, tl.entities)
    custom = CookieDB()
    custom.add("foo*")
    assert custom.name_is_tracking("foobar")
