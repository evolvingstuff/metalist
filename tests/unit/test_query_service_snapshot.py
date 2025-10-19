from app.services.query_service import NoteQueryService


class DummyDB:
    def commit(self):
        pass

    def rollback(self):
        pass


def test_collapsed_children_excluded_from_snapshot(monkeypatch):
    service = NoteQueryService(DummyDB())

    collapsed_tree = [
        {
            'id': 'collapsed-parent',
            'content': '<div>Parent</div>',
            'raw_content': '<div>Parent</div>',
            'parent_id': '',
            'children': [
                {
                    'id': 'hidden-child',
                    'content': '<div>Hidden</div>',
                    'raw_content': '<div>Hidden</div>',
                    'parent_id': 'collapsed-parent',
                    'children': [],
                    'flags': {'isCollapsed': False, 'isEditing': False},
                }
            ],
            'flags': {'isCollapsed': True, 'isEditing': False},
        },
        {
            'id': 'visible-parent',
            'content': '<div>Visible</div>',
            'raw_content': '<div>Visible</div>',
            'parent_id': '',
            'children': [
                {
                    'id': 'visible-child',
                    'content': '<div>Shown</div>',
                    'raw_content': '<div>Shown</div>',
                    'parent_id': 'visible-parent',
                    'children': [],
                    'flags': {'isCollapsed': False, 'isEditing': False},
                }
            ],
            'flags': {'isCollapsed': False, 'isEditing': False},
        },
    ]

    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: collapsed_tree)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    structure, payloads, locks = service.build_view_snapshot()

    ids = {entry['id'] for entry in structure}
    assert ids == {'collapsed-parent', 'visible-parent', 'visible-child'}
    assert 'hidden-child' not in ids

    assert set(payloads.keys()) == {'collapsed-parent', 'visible-parent', 'visible-child'}
    assert locks == {}


def test_collapsed_editing_includes_children(monkeypatch):
    service = NoteQueryService(DummyDB())

    tree = [
        {
            'id': 'collapsed-editing',
            'content': '<div>Parent</div>',
            'raw_content': '<div>Parent</div>',
            'parent_id': '',
            'children': [
                {
                    'id': 'editing-child',
                    'content': '<div>Child</div>',
                    'raw_content': '<div>Child</div>',
                    'parent_id': 'collapsed-editing',
                    'children': [],
                    'flags': {'isCollapsed': False, 'isEditing': False},
                }
            ],
            'flags': {'isCollapsed': True, 'isEditing': True},
        }
    ]

    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: tree)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    structure, payloads, _ = service.build_view_snapshot()

    ids = {entry['id'] for entry in structure}
    assert ids == {'collapsed-editing', 'editing-child'}
    assert set(payloads.keys()) == {'collapsed-editing', 'editing-child'}
