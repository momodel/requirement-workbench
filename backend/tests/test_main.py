import app.main as main_module


def test_configure_windows_asyncio_policy_sets_proactor(monkeypatch) -> None:
    calls = []

    class FakeCurrentPolicy:
        pass

    class FakeProactorPolicy:
        pass

    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.setattr(
        main_module.asyncio,
        "WindowsProactorEventLoopPolicy",
        FakeProactorPolicy,
        raising=False,
    )
    monkeypatch.setattr(
        main_module.asyncio,
        "get_event_loop_policy",
        lambda: FakeCurrentPolicy(),
    )
    monkeypatch.setattr(
        main_module.asyncio,
        "set_event_loop_policy",
        lambda policy: calls.append(policy),
    )

    main_module._configure_windows_asyncio_policy()

    assert len(calls) == 1
    assert isinstance(calls[0], FakeProactorPolicy)
