import app.services.query_service as query_service
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

    structure, payloads, locks = service.build_view_snapshot(client_seen_root_ids=set())

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

    structure, payloads, _ = service.build_view_snapshot(client_seen_root_ids=set())

    ids = {entry['id'] for entry in structure}
    assert ids == {'collapsed-editing', 'editing-child'}
    assert set(payloads.keys()) == {'collapsed-editing', 'editing-child'}


def _make_roots(count, *, collapsed=False):
    roots = []
    for i in range(count):
        roots.append(
            {
                'id': f'root-{i}',
                'content': '<div>Root</div>',
                'raw_content': '<div>Root</div>',
                'parent_id': '',
                'children': [],
                'flags': {'isCollapsed': collapsed, 'isEditing': False},
            }
        )
    return roots


def test_initial_window_limits_to_first_chunk(monkeypatch):
    service = NoteQueryService(DummyDB())
    roots = _make_roots(120)
    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: roots)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    structure, payloads, locks = service.build_view_snapshot(client_seen_root_ids=set())

    assert len(structure) == 50
    assert structure[-1]['id'] == 'root-49'
    assert set(payloads.keys()) == {entry['id'] for entry in structure}
    assert locks == {}


def test_window_extends_when_lowest_visible_near_tail(monkeypatch):
    service = NoteQueryService(DummyDB())
    roots = _make_roots(120)
    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: roots)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    structure, _, _ = service.build_view_snapshot(client_seen_root_ids={'root-40'})

    assert len(structure) == 100
    assert structure[-1]['id'] == 'root-99'


def test_known_root_extends_window(monkeypatch):
    service = NoteQueryService(DummyDB())
    roots = _make_roots(120)
    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: roots)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    structure, _, _ = service.build_view_snapshot(client_known_note_ids={'root-80'}, client_seen_root_ids=set())

    assert structure[-1]['id'] == 'root-80'


def test_editing_root_is_included(monkeypatch):
    service = NoteQueryService(DummyDB())
    roots = _make_roots(120)
    monkeypatch.setattr('app.services.query_service.build_note_tree', lambda *args, **kwargs: roots)
    monkeypatch.setattr('app.services.query_service.get_all_locks', lambda: {})

    monkeypatch.setattr(query_service, '_find_root_id', lambda note_id: 'root-75')

    structure, _, _ = service.build_view_snapshot(editing_note_id='note-any', client_seen_root_ids=set())

    assert structure[-1]['id'] == 'root-75'
