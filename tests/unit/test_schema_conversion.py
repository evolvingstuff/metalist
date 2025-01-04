from app.models.schema_conversion import OldSchemaNote, NewSchemaNote, old_to_new_schema, new_to_old_schema

def test_schema_conversion():
    # Create sample notes in old schema
    old_notes = [
        OldSchemaNote(id="1", content="Root 1", prev_id=None, next_id="2"),
        OldSchemaNote(id="2", content="Root 2", prev_id="1", next_id=None),
        OldSchemaNote(id="3", content="Child 1", prev_id=None, next_id="4", parent_id="2"),
        OldSchemaNote(id="4", content="Child 2", prev_id="3", next_id=None, parent_id="2"),
    ]
    
    # Convert to new schema
    new_notes = old_to_new_schema(old_notes)
    
    # Verify new schema properties
    assert len(new_notes) == 4
    assert new_notes[0].id == "1"
    assert new_notes[0].indent == 0
    assert new_notes[0].position < new_notes[1].position
    assert new_notes[1].id == "2"
    assert new_notes[1].indent == 0
    assert new_notes[2].id == "3"
    assert new_notes[2].indent == 1
    assert new_notes[2].position < new_notes[3].position
    assert new_notes[3].id == "4"
    assert new_notes[3].indent == 1
    
    # Convert back to old schema
    converted_old_notes = new_to_old_schema(new_notes)
    
    # Verify structure is preserved
    assert len(converted_old_notes) == 4
    for original, converted in zip(sorted(old_notes, key=lambda x: x.id), 
                                 sorted(converted_old_notes, key=lambda x: x.id)):
        assert original.id == converted.id
        assert original.content == converted.content
        assert original.prev_id == converted.prev_id
        assert original.next_id == converted.next_id
        assert original.parent_id == converted.parent_id 