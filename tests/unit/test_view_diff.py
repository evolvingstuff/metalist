from app.services.view_diff import generate_diff_ops
from app.services.view_state import ViewState


def build_state(children_by_parent, hash_by_id):
    structure = [
        {"id": note_id, "parentId": None, "prevId": None, "nextId": None, "hash": hash_by_id[note_id]}
        for note_id in hash_by_id
    ]
    payloads = {
        note_id: {"hash": hash, "flags": {}, "content": ""}
        for note_id, hash in hash_by_id.items()
    }
    return ViewState(
        structure=structure,
        payloads=payloads,
        locks={},
        children_by_parent=children_by_parent,
        hash_by_id=hash_by_id,
        metadata={},
    )


def test_generate_diff_ops_insert_new_root():
    previous = build_state({None: ['a']}, {'a': 'hash-a'})
    current = build_state({None: ['a', 'b']}, {'a': 'hash-a', 'b': 'hash-b'})

    ops = generate_diff_ops(previous, current)

    assert any(op for op in ops if op['type'] == 'insert' and op['noteId'] == 'b' and op['parentId'] is None and op['toIndex'] == 1)


def test_generate_diff_ops_remove_root():
    previous = build_state({None: ['a', 'b']}, {'a': 'hash-a', 'b': 'hash-b'})
    current = build_state({None: ['a']}, {'a': 'hash-a'})

    ops = generate_diff_ops(previous, current)

    assert any(op for op in ops if op['type'] == 'remove' and op['noteId'] == 'b' and op['parentId'] is None and op['fromIndex'] == 1)


def test_generate_diff_ops_nested_insert():
    previous = build_state({None: ['root']}, {'root': 'hash-root'})
    current = build_state({None: ['root'], 'root': ['child']}, {'root': 'hash-root', 'child': 'hash-child'})

    ops = generate_diff_ops(previous, current)

    assert any(op for op in ops if op['type'] == 'insert' and op['noteId'] == 'child' and op['parentId'] == 'root' and op['toIndex'] == 0)
