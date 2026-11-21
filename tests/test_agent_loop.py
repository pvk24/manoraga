"""Offline tests of the agent loop with a fake Claude client (no API key or network needed)."""
from types import SimpleNamespace as NS

import carnatic.agent as agent_mod
from carnatic.agent import CarnaticAgent
from carnatic.profile import ProfileStore


class FakeMessages:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def make_agent(tmp_path, monkeypatch, script):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    a = CarnaticAgent(user_id="t", profiles=ProfileStore(tmp_path / "p.db"))
    a.client = NS(messages=FakeMessages(script))
    return a


def text(t):
    return NS(type="text", text=t)


def test_web_search_is_limited_to_trusted_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "WEB_SEARCH", True)
    a = make_agent(tmp_path, monkeypatch, [NS(stop_reason="end_turn", content=[text("ok")])])
    a.ask("hi")
    tools = a.client.messages.calls[0]["tools"]
    ws = [t for t in tools if t.get("type", "").startswith("web_search")]
    assert len(ws) == 1
    assert set(ws[0]["allowed_domains"]) == {"karnatik.com", "shivkumar.org", "rasikas.org", "sangeethapriya.org", "wikipedia.org"}


def test_catalogue_only_mode_has_no_web_search(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "WEB_SEARCH", False)
    a = make_agent(tmp_path, monkeypatch, [NS(stop_reason="end_turn", content=[text("ok")])])
    a.ask("hi")
    assert not any(t.get("type", "").startswith("web_search") for t in a.client.messages.calls[0]["tools"])


def test_pause_turn_continues_and_records_search(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "WEB_SEARCH", True)
    search = NS(type="server_tool_use", id="s1", name="web_search", input={"query": "bhajare re manasa raga"})
    a = make_agent(tmp_path, monkeypatch, [
        NS(stop_reason="pause_turn", content=[search]),
        NS(stop_reason="end_turn", content=[text("According to Karnatik.com it is in Abheri.")]),
    ])
    assert "Abheri" in a.ask("Which raaga is Bhajare re manasa in?")
    assert a.tools.calls == ["web_search"]
    assert len(a.client.messages.calls) == 2


def test_prompt_forbids_assumptions_as_facts(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch, [])
    sys_prompt = a._system()
    assert "Never state an assumption as a fact" in sys_prompt and "source_links" in sys_prompt
