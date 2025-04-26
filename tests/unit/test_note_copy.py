from tests.unit.common import *
from app.models.utils import copy_note

def test_copy_single_note(db):
    """Test copying a single note with no children"""
    # Create a single note
    note = DBNote(id="1", content="Test Note")
    db.add(note)
    db.commit()
    
    # Copy the note
    new_id = copy_note(db, "1")
    
    # Verify the copy
    copied_note = db.get(DBNote, new_id)
    assert copied_note is not None
    assert copied_note.id != "1"
    assert copied_note.content == "Test Note"
    assert copied_note.parent_id is None
    assert copied_note.prev_id is None
    assert copied_note.next_id is None


def test_copy_note_with_children(db):
    """Test copying a note with direct children"""
    # Create parent note
    parent = DBNote(id="parent", content="Parent")
    
    # Create children
    child1 = DBNote(id="child1", content="Child 1", parent_id="parent")
    child2 = DBNote(id="child2", content="Child 2", parent_id="parent", prev_id="child1")
    child1.next_id = "child2"
    
    db.add_all([parent, child1, child2])
    db.commit()
    
    # Copy the parent note
    new_parent_id = copy_note(db, "parent")
    
    # Verify parent was copied
    copied_parent = db.get(DBNote, new_parent_id)
    assert copied_parent is not None
    assert copied_parent.content == "Parent"
    
    # Verify children were copied
    from app.models.linked_list import LinkedListManager
    children = LinkedListManager.get_ordered_child_list(db, new_parent_id)
    assert len(children) == 2
    
    # Verify child order and content
    assert children[0].content == "Child 1"
    assert children[1].content == "Child 2"
    
    # Verify child links
    assert children[0].prev_id is None
    assert children[0].next_id == children[1].id
    assert children[1].prev_id == children[0].id
    assert children[1].next_id is None


def test_deep_hierarchy_copy(db):
    """Test copying a deep hierarchy of notes"""
    # Create a deep hierarchy:
    # root
    #  └── level1
    #       └── level2
    #            └── level3
    root = DBNote(id="root", content="Root")
    level1 = DBNote(id="level1", content="Level 1", parent_id="root")
    level2 = DBNote(id="level2", content="Level 2", parent_id="level1")
    level3 = DBNote(id="level3", content="Level 3", parent_id="level2")
    
    db.add_all([root, level1, level2, level3])
    db.commit()
    
    # Copy the root
    new_root_id = copy_note(db, "root")
    
    # Verify full hierarchy was copied
    def count_descendants(parent_id):
        from app.models.linked_list import LinkedListManager
        children = LinkedListManager.get_ordered_child_list(db, parent_id)
        count = len(children)
        for child in children:
            count += count_descendants(child.id)
        return count
    
    # Original has 3 descendants
    assert count_descendants("root") == 3
    
    # Copy should also have 3 descendants
    assert count_descendants(new_root_id) == 3
    
    # Traverse the copied hierarchy to verify structure
    from app.models.linked_list import LinkedListManager
    
    level1_copies = LinkedListManager.get_ordered_child_list(db, new_root_id)
    assert len(level1_copies) == 1
    assert level1_copies[0].content == "Level 1"
    
    level2_copies = LinkedListManager.get_ordered_child_list(db, level1_copies[0].id)
    assert len(level2_copies) == 1
    assert level2_copies[0].content == "Level 2"
    
    level3_copies = LinkedListManager.get_ordered_child_list(db, level2_copies[0].id)
    assert len(level3_copies) == 1
    assert level3_copies[0].content == "Level 3"


def test_copy_with_siblings(db):
    """Test copying a note with multiple children that are siblings"""
    # Create a structure with siblings:
    # parent
    #  ├── child1
    #  ├── child2
    #  └── child3
    parent = DBNote(id="parent", content="Parent")
    child1 = DBNote(id="child1", content="Child 1", parent_id="parent")
    child2 = DBNote(id="child2", content="Child 2", parent_id="parent", prev_id="child1")
    child3 = DBNote(id="child3", content="Child 3", parent_id="parent", prev_id="child2")
    child1.next_id = "child2"
    child2.next_id = "child3"
    
    db.add_all([parent, child1, child2, child3])
    db.commit()
    
    # Copy the parent
    new_parent_id = copy_note(db, "parent")
    
    # Verify all children were copied with correct order
    from app.models.linked_list import LinkedListManager
    children = LinkedListManager.get_ordered_child_list(db, new_parent_id)
    assert len(children) == 3
    
    # Verify child order
    assert children[0].content == "Child 1"
    assert children[1].content == "Child 2"
    assert children[2].content == "Child 3"
    
    # Verify all links between siblings
    assert children[0].prev_id is None
    assert children[0].next_id == children[1].id
    assert children[1].prev_id == children[0].id
    assert children[1].next_id == children[2].id
    assert children[2].prev_id == children[1].id
    assert children[2].next_id is None


def test_copy_with_specific_parent(db):
    """Test copying a note to a specific new parent"""
    # Create two separate notes
    source = DBNote(id="source", content="Source")
    target = DBNote(id="target", content="Target")
    
    # Create a child under source
    child = DBNote(id="child", content="Child", parent_id="source")
    
    db.add_all([source, target, child])
    db.commit()
    
    # Copy source and its children, setting target as the new parent
    new_id = copy_note(db, "source", "target")
    
    # Verify the copy has target as parent
    copied_note = db.get(DBNote, new_id)
    assert copied_note.parent_id == "target"
    assert copied_note.content == "Source"
    
    # Verify the child was also copied
    from app.models.linked_list import LinkedListManager
    copied_children = LinkedListManager.get_ordered_child_list(db, new_id)
    assert len(copied_children) == 1
    assert copied_children[0].content == "Child"
    
    # Original structure should remain unchanged
    assert db.get(DBNote, "source").parent_id is None
    assert db.get(DBNote, "child").parent_id == "source"


def test_copy_nonexistent_note(db):
    """Test that copying a non-existent note raises an error"""
    with pytest.raises(ValueError, match="Source note with ID nonexistent not found"):
        copy_note(db, "nonexistent")