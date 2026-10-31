from army_bridge.policy import admission_denial, delegation_fingerprint, explicitly_mentioned, thread_root

USER = "@dsh-mini:army.local"
AGENT = "dsh-mini"
ALLOWED = {"@mo:army.local", "@hermes-mini:army.local", USER}
ROOMS = {"!room:army.local"}


def denial(content, sender="@mo:army.local", room="!room:army.local"):
    return admission_denial(
        content=content,
        sender=sender,
        room_id=room,
        user_id=USER,
        agent_id=AGENT,
        allowed_users=ALLOWED,
        allowed_rooms=ROOMS,
        allow_agent_senders=True,
    )


def test_structured_mention_is_accepted():
    assert denial({"msgtype": "m.text", "body": "hello", "m.mentions": {"user_ids": [USER]}}) is None


def test_matrix_pill_is_accepted():
    content = {
        "msgtype": "m.text",
        "body": "DSH Mini hello",
        "formatted_body": f'<a href="https://matrix.to/#/{USER}">DSH Mini</a> hello',
    }
    assert denial(content) is None


def test_plain_agent_handoff_is_accepted():
    assert denial({"msgtype": "m.text", "body": "@dsh-mini please review"}, sender="@hermes-mini:army.local") is None


def test_unmentioned_message_is_silent():
    assert denial({"msgtype": "m.text", "body": "please review"}) == "not_explicitly_mentioned"


def test_similar_agent_name_does_not_trigger():
    assert denial({"msgtype": "m.text", "body": "@dsh-mini-extra please review"}) == "not_explicitly_mentioned"


def test_room_mention_does_not_trigger():
    assert denial({"msgtype": "m.text", "body": "@room @dsh-mini please review"}) == "not_explicitly_mentioned"


def test_own_message_is_ignored():
    assert denial({"msgtype": "m.text", "body": "@dsh-mini loop"}, sender=USER) == "own_event"


def test_notice_is_ignored_even_with_mention():
    assert denial({"msgtype": "m.notice", "body": "@dsh-mini loop"}) == "not_plain_text"


def test_unknown_room_and_sender_are_ignored():
    assert denial({"msgtype": "m.text", "body": "@dsh-mini go"}, room="!other:army.local") == "room_not_allowed"
    assert denial({"msgtype": "m.text", "body": "@dsh-mini go"}, sender="@stranger:army.local") == "sender_not_allowed"


def test_thread_root_and_fingerprint():
    event = {"m.relates_to": {"rel_type": "m.thread", "event_id": "$root"}}
    assert thread_root(event, "$child") == "$root"
    assert thread_root({}, "$top") == "$top"
    assert delegation_fingerprint(USER, "$root", "Hello   world") == delegation_fingerprint(USER, "$root", "hello world")
