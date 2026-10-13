from studio import ops


def test_new_conversation():
    conv = ops.new_conversation()
    assert conv.title == "New chat"
    assert len(conv.branches) == 1
    assert conv.active_branch_id == conv.branches[0].id
    assert conv.branches[0].fork_of is None


def test_branch_and_rewind():
    conv = ops.new_conversation()
    main = conv.branches[0]
    m1 = ops.make_msg("user", "hello")
    m2 = ops.make_msg("assistant", "hi")
    main.messages = [m1, m2]

    b2 = ops.fork_branch(conv, main, None, "Branch")
    assert len(b2.messages) == 2
    assert b2.fork_of.message_id == m2.id

    r = ops.fork_branch(conv, main, m1.id, "Rewind")
    assert len(r.messages) == 1
    assert r.messages[0].id == m1.id
    assert r.fork_of.message_id == m1.id


def test_combine():
    conv = ops.new_conversation()
    main = conv.branches[0]
    main.messages = [ops.make_msg("user", "a")]
    b2 = ops.fork_branch(conv, main, None, "Branch")
    b2.messages.append(ops.make_msg("assistant", "b"))

    ops.combine_branches(conv, b2.id, main.id)
    assert len(conv.branches) == 1
    assert [m.content for m in main.messages] == ["a", "b"]
    assert conv.active_branch_id == main.id


def test_splice_summary():
    conv = ops.new_conversation()
    main = conv.branches[0]
    a = ops.make_msg("user", "aaaa")
    b = ops.make_msg("assistant", "bbbb")
    c = ops.make_msg("user", "cccc")
    main.messages = [a, b, c]

    s = ops.splice_summary(main, a.id, b.id, "summary")
    assert s.kind == "summary"
    assert len(main.messages) == 2
    assert main.messages[0].id == s.id
    assert main.messages[0].summary_of[0].id == a.id


def test_estimate_tokens():
    assert ops.estimate_tokens("abcd") == 1
    assert ops.estimate_tokens("abcde") == 2
